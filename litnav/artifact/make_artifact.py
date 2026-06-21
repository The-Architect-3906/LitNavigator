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
    evidence_by_concept: dict[str, list[str]] = {}
    citations: list[str] = []
    seen_citations: set[str] = set()

    for cid in ai.concept_ids:
        if cid not in id_to_concept:
            continue
        slug = slug_of[cid]
        evs: list[str] = []
        for chunk_row in conn.execute(
            "SELECT id, text FROM paper_chunks WHERE concept_id=? ORDER BY chunk_index, id",
            (cid,),
        ).fetchall():
            chunk_id, text = chunk_row
            evs.append(text)
            if chunk_id not in seen_citations:
                citations.append(chunk_id)
                seen_citations.add(chunk_id)
        evidence_by_concept[slug] = evs

    # ── 5. Build graph dict for mindmap renderer ──────────────────────────────
    graph = {"concepts": renderer_concepts, "edges": edges}

    # ── 6. Dispatch to renderer(s) ────────────────────────────────────────────
    if fmt == "mindmap":
        content = mindmap.render(graph, citations)

    elif fmt == "notes":
        content = notes.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id,
        )

    elif fmt == "slides":
        content = slides.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id,
        )

    elif fmt == "worked_example":
        content = worked_example.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id,
        )

    elif fmt == "combination":
        # mindmap + notes + worked_example concatenated into ONE file
        map_section = mindmap.render(graph, citations)
        notes_section = notes.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id,
        )
        worked_section = worked_example.render(
            renderer_concepts, evidence_by_concept, citations,
            conn=conn, session_id=session_id,
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
