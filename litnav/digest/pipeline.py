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
                 quiz_seeds: list[dict], misconceptions: list[dict],
                 slice_key: str | None = None) -> dict[str, int]:
    """Write concepts/edges/keypoints/quiz seeds/misconceptions as source='digested';
    return {slug: concept_id}."""
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
    # Build a mapping: concept_db_id -> set of resolved chunk ids, so we can tag
    # each written chunk with the concept that owns it after writing keypoints.
    # This is what makes retrieve_node (which filters paper_chunks by concept_id)
    # return evidence instead of 0 chunks (B18).
    concept_chunk_ids: dict[int, set[str]] = {cid: set() for cid in ids.values()}
    for k in keypoints:
        if k["concept_slug"] in ids:
            resolved = _norm_chunk_id(k.get("evidence_chunk_id"), valid_chunk_ids)
            repo.create_keypoint(conn, k["kp_id"], ids[k["concept_slug"]], k["name"],
                                 k.get("objective", ""),
                                 resolved,
                                 bloom_level=k.get("bloom_level", "recall"))
            if resolved:
                concept_chunk_ids[ids[k["concept_slug"]]].add(resolved)

    # Fallback: concepts that ended up with no evidence chunks linked (e.g. no
    # keypoints, or all keypoints had unresolvable ids that all collapsed to c0)
    # get their own chunk via round-robin over the source chunks not yet claimed.
    # This ensures every concept has at least one distinct, dedicated chunk so
    # retrieve_node always returns evidence (and the lesson doesn't cite another
    # concept's boilerplate text).
    if valid_chunk_ids:
        unclaimed = [cid for cid in valid_chunk_ids
                     if not any(cid in s for s in concept_chunk_ids.values())]
        concept_ids_without_chunks = [cid for cid, s in concept_chunk_ids.items() if not s]
        for i, concept_db_id in enumerate(concept_ids_without_chunks):
            if unclaimed:
                chunk_id = unclaimed.pop(0)
            else:
                # All chunks already claimed; assign round-robin from valid_chunk_ids
                chunk_id = valid_chunk_ids[i % len(valid_chunk_ids)]
            concept_chunk_ids[concept_db_id].add(chunk_id)

    # Tag each chunk with its owning concept so retrieve_node can filter by concept_id.
    for concept_db_id, chunk_ids in concept_chunk_ids.items():
        for chunk_id in chunk_ids:
            repo.assign_chunk_concept(conn, chunk_id, concept_db_id)

    for q in quiz_seeds:
        if q["concept_slug"] in ids:
            repo.create_quiz_item(conn, ids[q["concept_slug"]], q["question"], q["answer_key"],
                                  qtype=q.get("qtype", "explain"),
                                  keypoint_id=q.get("keypoint_id"),
                                  bloom_level=q.get("bloom_level", "recall"))
    for m in misconceptions:
        if m.get("concept_slug") in ids:
            repo.record_induced_misconception(
                conn,
                mid=m["id"],
                concept_id=ids[m["concept_slug"]],
                wrong_model=m["wrong_model"],
                correct_model=m["correct_model"],
                confidence=m.get("confidence", 0.6),
                evidence_chunk_id=_norm_chunk_id(m.get("evidence_chunk_id"), valid_chunk_ids),
                detect_hint=m.get("detect_hint"),
                reteach_strategy=m.get("reteach_strategy", "analogy"),
            )
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
                # RC#2/B3: derive a DISTINCT question for the missing rung — never a verbatim copy of
                # the base (which made the bloom-climb re-pose identical words). Live: LLM-generated;
                # offline: a deterministic reframe (the router fallback). Same answer_key/fact.
                "question": _derive_rung_question(base["question"], base["answer_key"], rung,
                                                  session_id=session_id, conn=conn, budget=budget),
                "answer_key": base["answer_key"],
                "bloom_level": rung,
            })
            have.add((kp_id, rung))

    return seeds


def _reframe_question(base_q: str, rung: str) -> str:
    """Deterministic, offline-safe reframe so a derived rung is never verbatim-identical to the base."""
    stem = base_q.rstrip(" ?").strip()
    if rung == "comprehension":
        return f"In your own words, explain why or how this holds: {stem}."
    if rung == "application":
        return f"Give a concrete example where this applies: {stem}."
    return f"Briefly, what is the key idea here? (re: {stem})"  # recall


def _derive_rung_question(base_q: str, answer_key: str, rung: str, *,
                          session_id, conn, budget) -> str:
    """A distinct question for `rung` grounded in the same fact. Live → LLM; offline → reframe fallback."""
    fallback = {"question": _reframe_question(base_q, rung)}
    spec = {"comprehension": "ask the learner to explain WHY/HOW or contrast with a misconception",
            "application": "give a concrete scenario and ask whether/how it applies",
            "recall": "ask directly what the key idea IS"}.get(rung, "ask a short-answer question")
    out = router.complete_json(
        f"Write ONE {rung}-level quiz question for the SAME fact, but clearly DIFFERENT wording from "
        f"the existing question. {spec}. JSON only.\n"
        f"Existing question: {base_q}\nKey idea / answer: {answer_key}\n"
        '{"question": "<distinct question text>"}',
        tier="cheap", stage="digest", fallback=fallback,
        session_id=session_id, conn=conn, budget=budget, cache=True,
    )
    q = (out.get("question") if isinstance(out, dict) else None) or fallback["question"]
    # guard: if the model echoed the base verbatim, fall back to the reframe
    return _reframe_question(base_q, rung) if q.strip() == base_q.strip() else q


def _seed_misconceptions(concepts: list[dict], candidate: dict, *,
                         session_id: str | None, conn: sqlite3.Connection | None,
                         budget: int | None) -> list[dict]:
    """LLM proposes one misconception per concept (live); offline returns candidate misconceptions.

    A4/B6: Without at least one seeded misconception per concept, _detect_misconception has an
    empty bank → detection never fires on digested concepts. Each misconception must carry a
    detect_hint regex so the keyword-match in grade.py / grade_kp.py can fire offline too.

    Each returned dict keys: id, concept_slug, wrong_model, correct_model, detect_hint,
    reteach_strategy, confidence, evidence_chunk_id.
    Confidence is ALWAYS rule-computed here (fixed 0.6 for digested); the LLM never sets it.
    """
    slug_lines = "\n".join(f"- {c['slug']}: {c.get('name', c['slug'])}" for c in concepts)
    prompt = (
        "For each concept below, identify ONE common misconception a learner holds when first "
        "encountering it. Provide: the wrong belief (wrong_model), the correct replacement "
        "(correct_model), and a detect_hint — a short regex (2-4 alternated keywords, e.g. "
        "'keyword1|keyword2') that would match a learner's answer that voices that wrong belief.\n"
        f"Concepts:\n{slug_lines}\n\n"
        'Respond JSON: {"misconceptions": [{"concept_slug", "wrong_model", "correct_model", '
        '"detect_hint", "reteach_strategy": "analogy"}]}'
    )
    fallback = {"misconceptions": candidate.get("misconceptions", [])}
    result = router.complete_json(prompt, tier="cheap", stage="digest", fallback=fallback,
                                  session_id=session_id, conn=conn, budget=budget, cache=True)
    raw = result.get("misconceptions") if isinstance(result, dict) else None
    if not isinstance(raw, list):
        raw = candidate.get("misconceptions", [])

    slugs = {c["slug"] for c in concepts}
    items = [dict(m) for m in raw
             if isinstance(m, dict) and m.get("concept_slug") in slugs
             and m.get("wrong_model") and m.get("correct_model")]

    # Fall back to the candidate when the LLM returned nothing usable.
    if not items:
        items = [dict(m) for m in candidate.get("misconceptions", [])
                 if isinstance(m, dict) and m.get("concept_slug") in slugs]

    # Guarantee ≥1 entry per concept: synthesise a stub for any that are still missing.
    covered = {m["concept_slug"] for m in items}
    for c in concepts:
        if c["slug"] not in covered:
            items.append({
                "concept_slug": c["slug"],
                "wrong_model": f"Learners often confuse or over-generalise {c.get('name', c['slug'])}.",
                "correct_model": (
                    f"A precise understanding of {c.get('name', c['slug'])} requires "
                    "attending to the specific mechanism described in the source."
                ),
                "detect_hint": c["slug"].replace("_", "|"),
                "reteach_strategy": "analogy",
            })

    # Assign stable ids and fixed confidence; strip LLM-emitted confidence if any.
    for i, m in enumerate(items):
        m["id"] = f"dg_{m['concept_slug']}_{i}"
        m["confidence"] = 0.6          # rule-computed, not LLM-emitted
        m.setdefault("evidence_chunk_id", None)
        m.setdefault("reteach_strategy", "analogy")

    return items


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
    misconceptions = _seed_misconceptions(concepts, candidate,
                                          session_id=session_id, conn=conn, budget=budget)

    if write:
        _write_graph(conn, di, concepts, verified, keypoints, quiz_seeds, misconceptions,
                     slice_key=key)
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
