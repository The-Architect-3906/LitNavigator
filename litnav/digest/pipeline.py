"""DIGEST orchestrator (OW-2).

cache check -> extract -> edges -> edge_accuracy (pre-downgrade) -> verify -> assemble -> write graph
(source='digested') -> cache_put. Just-in-time and sliced: only di.target_slugs are treated as the
goal slice for high-impact verification. Deterministic + $0 with provider=none (every stage replays the
candidate). Every LLM/embedding call is metered through the router.
"""
from __future__ import annotations

import sqlite3

from litnav.digest.contract import DigestInput, DigestResult, slice_key
from litnav.digest import extract, edges as edges_mod, verify as verify_mod
from litnav.storage import repo, openworld_repo


def _slice_key(di: DigestInput) -> str:
    return slice_key(di.domain_key, [s.source_id for s in di.sources], di.target_slugs)


def _write_graph(conn: sqlite3.Connection, di: DigestInput, concepts: list[dict],
                 scored_edges: list[dict], keypoints: list[dict],
                 quiz_seeds: list[dict]) -> dict[str, int]:
    """Write concepts/edges/keypoints/quiz seeds as source='digested'; return {slug: concept_id}."""
    ids: dict[str, int] = {}
    for c in concepts:
        existing = repo.get_concept_by_slug(conn, c["slug"])
        if existing:
            ids[c["slug"]] = existing["id"]
            continue
        cid = repo.next_concept_id(conn)
        repo.create_concept(conn, cid, c["slug"], c["name"], c.get("frontier_flag"),
                            source="digested", domain=c.get("domain", di.domain_key))
        ids[c["slug"]] = cid
    for e in scored_edges:
        if e["prereq_slug"] in ids and e["target_slug"] in ids:
            repo.record_edge(conn, ids[e["prereq_slug"]], ids[e["target_slug"]],
                             edge_type=e["edge_type"], source="digested",
                             confidence=e["confidence"], evidence_chunks=e["evidence"])
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


def digest(di: DigestInput, *, conn: sqlite3.Connection, candidate: dict,
           session_id: str | None = None, budget: int | None = None,
           write: bool = True) -> DigestResult:
    key = _slice_key(di)
    cached = openworld_repo.cache_get(conn, key)
    if cached and cached["status"] == "cached":
        return DigestResult(di.domain_key, [], [], [], [], [], edge_accuracy=1.0, cache_hit=True)

    concepts, keypoints = extract.extract_concepts(di, candidate=candidate,
                                                   session_id=session_id, conn=conn, budget=budget)
    scored = edges_mod.build_edges(di, concepts, candidate=candidate,
                                   session_id=session_id, conn=conn, budget=budget)
    labels = candidate.get("judge_labels", {})
    accuracy = verify_mod.edge_accuracy(scored, judge_labels=labels, session_id=session_id,
                                        conn=conn, budget=budget)           # BEFORE downgrade
    verified, unverified = verify_mod.verify_edges(scored, judge_labels=labels,
                                                   session_id=session_id, conn=conn, budget=budget)
    quiz_seeds = candidate.get("quiz_seeds", [])

    if write:
        _write_graph(conn, di, concepts, verified, keypoints, quiz_seeds)
        openworld_repo.cache_put(conn, key)

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
