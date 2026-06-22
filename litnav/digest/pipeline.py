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


def _norm_chunk_id(raw, valid_ids: list[str]) -> str | None:
    """Map an LLM-emitted keypoint evidence_chunk_id onto a REAL written chunk id.

    The extractor often returns bare indices ('1', 1, 'c3') that don't match the global
    'c{idx}' ids we actually write, or hallucinates indices when there are fewer chunks than
    keypoints. We resolve to a real chunk so evidence/citations link (else artifacts come out
    empty — the OW-5.1 linkage bug). Unresolvable ids fall back to the first chunk (cite the
    source) rather than dangling.
    """
    if not valid_ids:
        return None
    if raw in valid_ids:
        return raw
    try:
        i = int(str(raw).lstrip("cC"))
    except (TypeError, ValueError):
        return valid_ids[0]
    for cand in (f"c{i}", f"c{i - 1}"):   # tolerate 0- vs 1-indexed
        if cand in valid_ids:
            return cand
    return valid_ids[0]


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
    # Global chunk ids written by _write_sources: c0..c{total-1}. Used to normalize keypoint
    # evidence_chunk_id onto real chunks so evidence/citations resolve downstream.
    total_chunks = sum(len(s.chunks) for s in di.sources)
    valid_chunk_ids = [f"c{i}" for i in range(total_chunks)]
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
                                 k.get("objective", ""),
                                 _norm_chunk_id(k.get("evidence_chunk_id"), valid_chunk_ids),
                                 bloom_level=k.get("bloom_level", "recall"))
    for q in quiz_seeds:
        if q["concept_slug"] in ids:
            repo.create_quiz_item(conn, ids[q["concept_slug"]], q["question"], q["answer_key"],
                                  qtype=q.get("qtype", "explain"),
                                  keypoint_id=q.get("keypoint_id"),
                                  bloom_level=q.get("bloom_level", "recall"))
    return ids


# Map free-form / non-ladder bloom labels onto the assess ladder (litnav.state.BLOOM_LADDER).
_BLOOM_ALIAS = {
    "remember": "recall", "knowledge": "recall", "recall": "recall",
    "understand": "comprehension", "comprehension": "comprehension",
    "apply": "application", "application": "application", "analyze": "application",
}


def _propose_quiz_seeds(concepts: list[dict], by_chunk: dict, candidate: dict, *,
                        keypoints: list[dict] | None = None,
                        session_id: str | None, conn: sqlite3.Connection | None,
                        budget: int | None) -> list[dict]:
    """LLM proposes one seed question per concept (live); offline returns candidate quiz_seeds.

    A1/B1: a single recall seed per concept caps the learner at ONE correct observation
    (kp_confidence(1)=0.30 < KP_CONF_THRESHOLD), so digested concepts always conceded. We
    normalize bloom labels to the assess ladder and guarantee each keypoint carries BOTH a
    recall and a comprehension seed, attached to that keypoint, so the bloom-climb has a real
    second question to pose offline → ≥2 correct observations → mastery is reachable.
    """
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
    seeds = [dict(s) for s in seeds if isinstance(s, dict) and s.get("concept_slug") in slugs]

    # Normalize bloom labels onto the assess ladder so cached seeds are reachable by the climb.
    for s in seeds:
        s["bloom_level"] = _BLOOM_ALIAS.get(str(s.get("bloom_level", "recall")).lower(), "recall")

    # Attach each seed to its concept's first keypoint when the LLM/candidate left it unbound,
    # then ensure every keypoint has BOTH a recall and a comprehension seed.
    kps = keypoints or []
    first_kp_for_slug: dict[str, str] = {}
    for k in kps:
        first_kp_for_slug.setdefault(k.get("concept_slug"), k.get("kp_id"))
    for s in seeds:
        if not s.get("keypoint_id"):
            s["keypoint_id"] = first_kp_for_slug.get(s.get("concept_slug"))

    # Index existing (keypoint_id, bloom) coverage; fill recall + comprehension gaps per keypoint.
    have: set[tuple[str | None, str]] = {(s.get("keypoint_id"), s["bloom_level"]) for s in seeds}
    by_kp: dict[str, dict] = {}
    for s in seeds:
        if s.get("keypoint_id"):
            by_kp.setdefault(s["keypoint_id"], s)
    for k in kps:
        kp_id, slug = k.get("kp_id"), k.get("concept_slug")
        if not kp_id:
            continue
        base = by_kp.get(kp_id)
        for rung in ("recall", "comprehension"):
            if (kp_id, rung) in have:
                continue
            if base is None:
                continue   # no seed text to derive from; assess_next will LLM-generate live
            seeds.append({
                "concept_slug": slug,
                "keypoint_id": kp_id,
                "question": base["question"],
                "answer_key": base["answer_key"],
                "bloom_level": rung,
            })
            have.add((kp_id, rung))

    return seeds


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
    quiz_seeds = _propose_quiz_seeds(concepts, {}, candidate, keypoints=keypoints,
                                     session_id=session_id, conn=conn, budget=budget)

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
