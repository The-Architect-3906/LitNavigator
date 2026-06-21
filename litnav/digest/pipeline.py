"""DIGEST orchestrator (OW-2).

cache check -> extract -> edges -> edge_accuracy (pre-downgrade) -> verify -> assemble -> write graph
(source='digested') -> cache_put. Just-in-time and sliced: only di.target_slugs are treated as the
goal slice for high-impact verification. Deterministic + $0 with provider=none (every stage replays the
candidate). Every LLM/embedding call is metered through the router.
"""
from __future__ import annotations

import os
import sqlite3

from litnav.digest.contract import DigestInput, DigestResult, slice_key
from litnav.digest import extract, edges as edges_mod, verify as verify_mod
from litnav.llm import router
from litnav.storage import repo, openworld_repo


def _model_key() -> str:
    return os.getenv("LITNAV_LLM_PROVIDER", "none") + "|" + os.getenv("LITNAV_LLM_MODEL", "gpt-4o-mini")


def _slice_key(di: DigestInput) -> str:
    return slice_key(di.domain_key, [s.source_id for s in di.sources], di.target_slugs)


def _write_sources(conn: sqlite3.Connection, di: DigestInput) -> None:
    """Insert a papers row per source + paper_chunks (global c0,c1,... ids) so digested
    evidence_chunk_id references resolve to real text."""
    idx = 0
    for s in di.sources:
        # Check for an existing paper by source_id to avoid duplicate rows on re-digest
        existing_row = conn.execute(
            "SELECT id FROM papers WHERE source_id=?", (s.source_id,)
        ).fetchone()
        if existing_row:
            pid = existing_row[0]
        else:
            pid = repo.create_paper(
                conn,
                source_id=s.source_id,
                arxiv_id=(s.source_id if s.source_type == "arxiv" else None),
                title=s.title,
                source_type=s.source_type,
                url=s.url,
            )
        for ci, text in enumerate(s.chunks):
            repo.create_paper_chunk(conn, f"c{idx}", pid, None, text, chunk_index=ci)
            idx += 1


def _write_graph(conn: sqlite3.Connection, di: DigestInput, concepts: list[dict],
                 scored_edges: list[dict], keypoints: list[dict],
                 quiz_seeds: list[dict], slice_key: str | None = None) -> dict[str, int]:
    """Write concepts/edges/keypoints/quiz seeds as source='digested'; return {slug: concept_id}."""
    _write_sources(conn, di)
    ids: dict[str, int] = {}
    for c in concepts:
        existing = repo.get_concept_by_slug(conn, c["slug"])
        if existing:
            ids[c["slug"]] = existing["id"]
            continue
        cid = repo.next_concept_id(conn)
        repo.create_concept(conn, cid, c["slug"], c["name"], c.get("frontier_flag"),
                            source="digested", domain=c.get("domain", di.domain_key),
                            slice_key=slice_key)
        ids[c["slug"]] = cid
    # Edges are written INSERT-OR-IGNORE on PK (prereq, target, edge_type). A prereq edge that
    # verify_edges downgraded to 'similarity' can therefore collide with a pre-existing similarity
    # edge on the same (A,B) pair — first writer wins, silently. Task 8's gate exercises this.
    for e in scored_edges:
        if e["prereq_slug"] in ids and e["target_slug"] in ids:
            repo.record_edge(conn, ids[e["prereq_slug"]], ids[e["target_slug"]],
                             edge_type=e["edge_type"], source="digested",
                             confidence=e["confidence"], evidence_chunks=e["evidence"],
                             slice_key=slice_key)
    for k in keypoints:
        if k["concept_slug"] in ids:
            repo.create_keypoint(conn, k["kp_id"], ids[k["concept_slug"]], k["name"],
                                 k.get("objective", ""), k.get("evidence_chunk_id"),
                                 bloom_level=k.get("bloom_level", "recall"))
    for q in quiz_seeds:
        if q["concept_slug"] in ids:
            repo.create_quiz_item(conn, ids[q["concept_slug"]], q["question"], q["answer_key"],
                                  qtype=q.get("qtype", "explain"),
                                  keypoint_id=q.get("keypoint_id"),
                                  bloom_level=q.get("bloom_level", "recall"))
    return ids


def _propose_quiz_seeds(concepts: list[dict], by_chunk: dict, candidate: dict, *,
                        session_id: str | None, conn: sqlite3.Connection | None,
                        budget: int | None) -> list[dict]:
    """LLM proposes one seed question per concept (live); offline returns candidate quiz_seeds."""
    slug_lines = "\n".join(f"- {c['slug']}: {c.get('name', c['slug'])}" for c in concepts)
    prompt = (
        "For each concept below, write ONE short recall-level seed question and its answer, "
        "grounded in the evidence. Use only these concept slugs.\n"
        f"Concepts:\n{slug_lines}\n\n"
        'Respond JSON: {"quiz_seeds": [{"concept_slug","question","answer_key","bloom_level":"recall"}]}'
    )
    fallback = {"quiz_seeds": candidate.get("quiz_seeds", [])}
    result = router.complete_json(prompt, tier="cheap", stage="digest", fallback=fallback,
                                  session_id=session_id, conn=conn, budget=budget, cache=True)
    seeds = result.get("quiz_seeds") if isinstance(result, dict) else None
    if not isinstance(seeds, list):
        seeds = candidate.get("quiz_seeds", [])
    slugs = {c["slug"] for c in concepts}
    return [s for s in seeds if isinstance(s, dict) and s.get("concept_slug") in slugs]


def digest(di: DigestInput, *, conn: sqlite3.Connection, candidate: dict,
           session_id: str | None = None, budget: int | None = None,
           write: bool = True, model_key: str | None = None) -> DigestResult:
    """Digest a source slice into the concept graph and return a DigestResult.

    Cache-hit fast path: when the slice is already digested with the same model_key, re-reads
    the slice graph from the DB and returns it with cache_hit=True. If the model_key differs,
    falls through to a full re-digest.
    """
    key = _slice_key(di)
    mk = model_key or _model_key()
    cached = openworld_repo.cache_get(conn, key)
    if cached and cached["status"] == "cached" and cached.get("model_key") == mk:
        g = repo.get_slice_graph(conn, key)
        return DigestResult(di.domain_key, g["concepts"], g["edges"], [], [], [],
                            edge_accuracy=1.0, cache_hit=True)

    concepts, keypoints = extract.extract_concepts(di, candidate=candidate,
                                                   session_id=session_id, conn=conn, budget=budget)
    scored = edges_mod.build_edges(di, concepts, candidate=candidate,
                                   session_id=session_id, conn=conn, budget=budget,
                                   keypoints=keypoints)
    labels = candidate.get("judge_labels", {})
    from litnav.digest import refd as refd_mod
    _by_chunk = {}
    _i = 0
    for s in di.sources:
        for ch in s.chunks:
            _by_chunk[f"c{_i}"] = ch; _i += 1
    refd_scores = refd_mod.refd_scores(concepts, _by_chunk)
    accuracy, (verified, unverified) = verify_mod.verify_pass(
        scored, judge_labels=labels, session_id=session_id, conn=conn, budget=budget, refd=refd_scores)
    quiz_seeds = _propose_quiz_seeds(concepts, {}, candidate, session_id=session_id,
                                     conn=conn, budget=budget)

    if write:
        _write_graph(conn, di, concepts, verified, keypoints, quiz_seeds, slice_key=key)
        openworld_repo.cache_put(conn, key, model_key=mk)

    return DigestResult(
        domain_key=di.domain_key,
        concepts=concepts,
        edges=verified,
        keypoints=keypoints,
        quiz_seeds=quiz_seeds,
        unverified_edges=unverified,
        edge_accuracy=accuracy,
        cache_hit=False,
    )
