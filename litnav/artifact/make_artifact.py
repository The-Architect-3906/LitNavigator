"""make_artifact orchestrator (spec §6.4).

Pipeline:
  1. select format (via selector or override)
  2. gather concepts, edges, evidence, citations from SQLite
  3. dispatch to the appropriate renderer(s)
  4. write the resulting Markdown to out_dir/<fmt>.md
  5. return ArtifactResult(artifact_path, format, citations)
"""
from __future__ import annotations

import os
import sqlite3

from litnav.artifact.contract import ArtifactInput, ArtifactResult
from litnav.artifact.selector import select_format
from litnav.artifact.renderers import mindmap, notes, worked_example, slides


def make_artifact(
    ai: ArtifactInput,
    *,
    conn: sqlite3.Connection,
    session_id: str,
    out_dir: str,
) -> ArtifactResult:
    """Orchestrate artifact generation for the given ArtifactInput.

    Parameters
    ----------
    ai:
        Input: concept IDs, scenario dict, optional format override.
    conn:
        Open SQLite connection (must have been initialised with init_db).
    session_id:
        Used for LLM cost metering (passed through to renderers).
    out_dir:
        Directory where the output ``.md`` file will be written.
    """
    # ── 1. Select format ──────────────────────────────────────────────────────
    fmt = select_format(ai.scenario, override=ai.format)

    # ── 2. Gather concepts (preserve input order; skip missing ids) ───────────
    id_to_concept: dict[int, dict] = {}
    for cid in ai.concept_ids:
        row = conn.execute(
            "SELECT id, slug, name FROM concepts WHERE id=?", (cid,)
        ).fetchone()
        if row:
            id_to_concept[row[0]] = {"slug": row[1], "name": row[2]}

    # Ordered list matching concept_ids order
    renderer_concepts: list[dict] = [
        id_to_concept[cid] for cid in ai.concept_ids if cid in id_to_concept
    ]
    selected_ids = set(id_to_concept.keys())
    slug_of: dict[int, str] = {cid: id_to_concept[cid]["slug"] for cid in selected_ids}

    # ── 3. Gather edges (only those fully inside the selected concept set) ─────
    edges: list[dict] = []
    for row in conn.execute(
        "SELECT prereq_concept, target_concept, edge_type FROM concept_edges"
    ).fetchall():
        prereq_id, target_id, edge_type = row
        if prereq_id in selected_ids and target_id in selected_ids:
            edges.append({
                "prereq_slug": slug_of[prereq_id],
                "target_slug": slug_of[target_id],
                "edge_type": edge_type,
            })

    # ── 4. Gather evidence + citations ────────────────────────────────────────
    # Evidence comes from THREE linkages, because digested data and hand-seeded fixtures
    # store the concept→evidence relation differently:
    #   (a) keypoint name/objective — concept-specific, LLM-grounded teachable statements (digest);
    #   (b) paper_chunks.concept_id — chunks tagged with the concept (fixtures / curated);
    #   (c) keypoints.evidence_chunk_id → paper_chunks.text — the digest's real chunk linkage.
    # A citation is kept only if its chunk id resolves to a real paper_chunks row.
    evidence_by_concept: dict[str, list[str]] = {}
    citations: list[str] = []
    seen_citations: set[str] = set()

    # Source-chunk pool: every digested concept was EXTRACTED from these chunks, so they are
    # valid grounding when a concept carries no keypoint/concept-tagged evidence of its own
    # (LLM keypoint extraction is sparse/non-deterministic). Without this, artifacts fall back
    # to ungrounded LLM generation with no citations — "bluffing" (OW-5.1).
    source_pool = conn.execute(
        "SELECT id, text FROM paper_chunks ORDER BY chunk_index, id"
    ).fetchall()
    _POOL_FALLBACK_N = 3

    def _add_citation(chunk_id) -> None:
        if not chunk_id or chunk_id in seen_citations:
            return
        if conn.execute("SELECT 1 FROM paper_chunks WHERE id=?", (chunk_id,)).fetchone():
            citations.append(chunk_id)
            seen_citations.add(chunk_id)

    for cid in ai.concept_ids:
        if cid not in id_to_concept:
            continue
        slug = slug_of[cid]
        evs: list[str] = []
        seen_ev: set[str] = set()

        def _add_ev(text: str | None) -> None:
            t = (text or "").strip()
            if t and t not in seen_ev:
                evs.append(t)
                seen_ev.add(t)

        # (a) keypoint objectives/names (concept-specific) + their chunk citations
        for kp in conn.execute(
            "SELECT name, objective, evidence_chunk_id FROM keypoints "
            "WHERE concept_id=? ORDER BY sort_order, id", (cid,),
        ).fetchall():
            kp_name, kp_obj, kp_ecid = kp
            _add_ev(kp_obj or kp_name)
            _add_citation(kp_ecid)
        # (c) text of chunks linked via keypoints (digest path)
        for chunk_row in conn.execute(
            "SELECT pc.id, pc.text FROM keypoints kp JOIN paper_chunks pc "
            "ON pc.id = kp.evidence_chunk_id WHERE kp.concept_id=? ORDER BY pc.chunk_index, pc.id",
            (cid,),
        ).fetchall():
            _add_ev(chunk_row[1])
            _add_citation(chunk_row[0])
        # (b) chunks tagged directly with the concept (fixture / curated path)
        for chunk_row in conn.execute(
            "SELECT id, text FROM paper_chunks WHERE concept_id=? ORDER BY chunk_index, id",
            (cid,),
        ).fetchall():
            _add_ev(chunk_row[1])
            _add_citation(chunk_row[0])

        # Fallback: no concept-specific evidence -> ground in the source chunks it came from.
        if not evs and source_pool:
            for pool_id, pool_text in source_pool[:_POOL_FALLBACK_N]:
                _add_ev(pool_text)
                _add_citation(pool_id)

        evidence_by_concept[slug] = evs

    # ── 5. Collect Bloom level per concept (highest level reached in keypoints) ─
    _bloom_order = {"recall": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}
    bloom_by_concept: dict[str, str] = {}
    for cid in ai.concept_ids:
        if cid not in id_to_concept:
            continue
        slug = slug_of[cid]
        rows = conn.execute(
            "SELECT bloom_level FROM keypoints WHERE concept_id=?", (cid,)
        ).fetchall()
        if rows:
            highest = max((r[0] or "recall" for r in rows), key=lambda b: _bloom_order.get(b, 0))
            bloom_by_concept[slug] = highest

    # ── 6. Build graph dict for mindmap renderer ──────────────────────────────
    graph = {"concepts": renderer_concepts, "edges": edges}

    # ── 7. Dispatch to renderer(s) ────────────────────────────────────────────
    lang = ai.language or "English"

    if fmt == "mindmap":
        content = mindmap.render(graph, citations)

    elif fmt == "notes":
        content = notes.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id, language=lang,
            edges=edges, bloom_by_concept=bloom_by_concept,
        )

    elif fmt == "slides":
        content = slides.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id, language=lang,
        )

    elif fmt == "worked_example":
        content = worked_example.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id, language=lang,
        )

    elif fmt == "combination":
        # mindmap + notes + worked_example concatenated into ONE file
        map_section = mindmap.render(graph, citations)
        notes_section = notes.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id, language=lang,
            edges=edges, bloom_by_concept=bloom_by_concept,
        )
        worked_section = worked_example.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id, language=lang,
        )
        content = "\n\n---\n\n".join([map_section, notes_section, worked_section])

    else:
        # Fallback — should not happen if FORMATS is kept in sync
        content = mindmap.render(graph, citations)

    # ── 7. Write file ─────────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    artifact_path = os.path.join(out_dir, f"{fmt}.md")
    with open(artifact_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return ArtifactResult(artifact_path=artifact_path, format=fmt, citations=citations)
