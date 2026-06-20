"""DIGEST stage 2 — typed edges (prerequisite + similarity) with transparent confidence.

Confidence is ALWAYS computed by induced_confidence (reused verbatim from the M3 induction path);
the LLM may only label evidence strength. Prereq + similarity edges are now LLM-PROPOSED over the
EXTRACTED concept slugs live (open-world capability); the candidate is the offline fallback (mirrors
induce._extract_misconception: LLM proposes, candidate is fallback, confidence is rule-computed).
Similarity edges are additionally cosine-filtered over concept-name embeddings live.
"""
from __future__ import annotations

import math
import sqlite3

from litnav.digest.contract import DigestInput, HIGH_IMPACT_MIN_CONF
from litnav.nodes.induce import induced_confidence
from litnav.llm import router

# Mirror of induce's strength keys (declared locally to avoid importing a private name).
_VALID_STRENGTH = {"weak_hint", "general_statement", "explicit_assertion"}
_SIM_COS_MIN = 0.55   # heuristic: below this cosine, two concepts are not "similar" (tune via edge-accuracy)


def _label_strength(chunk_texts: list[str], fallback: str, *, session_id, conn, budget) -> str:
    """Metered analogue of induce._label_strength — cheap tier, candidate fallback."""
    prompt = (
        "Rate how strongly the evidence asserts the prerequisite relation it is cited for.\n"
        f"Evidence: {chunk_texts}\n"
        'Respond as JSON: {"max_strength": "weak_hint" | "general_statement" | "explicit_assertion"}'
    )
    result = router.complete_json(prompt, tier="cheap", stage="digest",
                                  fallback={"max_strength": fallback}, session_id=session_id,
                                  conn=conn, budget=budget)
    labelled = result.get("max_strength", fallback) if isinstance(result, dict) else fallback
    return labelled if labelled in _VALID_STRENGTH else fallback


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def _propose_edges(concepts: list[dict], by_chunk: dict, candidate: dict, *,
                   session_id, conn, budget) -> dict:
    """LLM proposes prereq + similarity edges over the EXTRACTED concept slugs (live);
    offline (provider=none) the router returns the candidate as fallback."""
    slug_lines = "\n".join(f"- {c['slug']}: {c.get('name', c['slug'])}" for c in concepts)
    chunks_txt = "\n".join(f"[{cid}] {txt}" for cid, txt in by_chunk.items())
    prompt = (
        "Given these concepts extracted from the evidence, propose edges BETWEEN THEM ONLY.\n"
        "A prerequisite edge means the prereq concept must be understood before the target.\n"
        "A similarity edge links two closely related concepts.\n"
        f"Concepts (use these slugs as endpoints, nothing else):\n{slug_lines}\n\n"
        f"Evidence chunks (cite their ids):\n{chunks_txt}\n\n"
        'Respond JSON: {"prereq_edges": [{"prereq_slug","target_slug","evidence_chunks":[ids],'
        '"max_strength":"weak_hint|general_statement|explicit_assertion","multi_paper":bool}], '
        '"similarity_edges": [{"a_slug","b_slug","evidence_chunks":[ids],"max_strength","multi_paper":bool}]}'
    )
    fallback = {"prereq_edges": candidate.get("prereq_edges", []),
                "similarity_edges": candidate.get("similarity_edges", [])}
    result = router.complete_json(prompt, tier="cheap", stage="digest", fallback=fallback,
                                  session_id=session_id, conn=conn, budget=budget)
    if not isinstance(result, dict):
        return fallback
    return {"prereq_edges": result.get("prereq_edges") or [],
            "similarity_edges": result.get("similarity_edges") or []}


def build_edges(di: DigestInput, concepts: list[dict], *, candidate: dict,
                session_id: str | None, conn: sqlite3.Connection | None,
                budget: int | None = None) -> list[dict]:
    """Return scored edge dicts: {prereq_slug, target_slug, edge_type, evidence, max_strength,
    confidence, high_impact}."""
    # Global running chunk index (c0, c1, c2, ...) across ALL sources — must NOT restart per source.
    by_chunk: dict[str, str] = {}
    _i = 0
    for s in di.sources:
        for ch in s.chunks:
            by_chunk[f"c{_i}"] = ch
            _i += 1

    slugs = {c["slug"] for c in concepts}
    targets = set(di.target_slugs) if di.target_slugs else slugs   # [] => whole slice is the target
    out: list[dict] = []

    # LLM proposes edges over the extracted concept slugs (live); offline: candidate is the fallback.
    proposed = _propose_edges(concepts, by_chunk, candidate, session_id=session_id,
                              conn=conn, budget=budget)

    # --- prerequisite edges ---
    for e in proposed["prereq_edges"]:
        if e["prereq_slug"] not in slugs or e["target_slug"] not in slugs:
            continue
        # Clean evidence: keep only chunk ids that actually exist in this digest run.
        cleaned = [ci for ci in e["evidence_chunks"] if ci in by_chunk]
        if not cleaned:
            continue                                   # no real evidence -> drop edge
        strength = e.get("max_strength", "general_statement")
        if strength not in _VALID_STRENGTH:
            strength = "general_statement"
        conf = induced_confidence(len(cleaned), strength, e.get("multi_paper", False))
        out.append({
            "prereq_slug": e["prereq_slug"], "target_slug": e["target_slug"],
            "edge_type": "prerequisite", "evidence": cleaned, "max_strength": strength,
            "confidence": conf,
            "high_impact": conf >= HIGH_IMPACT_MIN_CONF and e["target_slug"] in targets,
        })

    # --- similarity edges (KnowLP fallback edges) ---
    name_vecs = None
    if conn is not None:                               # live: try real cosine; offline returns None
        name_vecs = router.embed_texts([c["name"] for c in concepts], stage="digest",
                                       session_id=session_id, conn=conn, budget=budget)
    centroid = {c["slug"]: v for c, v in zip(concepts, name_vecs)} if name_vecs else {}
    for e in proposed["similarity_edges"]:
        a, b = e["a_slug"], e["b_slug"]
        if a not in slugs or b not in slugs:
            continue
        # Clean evidence: keep only chunk ids that actually exist in this digest run.
        cleaned = [ci for ci in e["evidence_chunks"] if ci in by_chunk]
        if not cleaned:
            continue                                   # no real evidence -> drop edge
        if (centroid and a in centroid and b in centroid
                and _cosine(centroid[a], centroid[b]) < _SIM_COS_MIN):
            continue                                   # live: drop pairs that are not actually close
        strength = e.get("max_strength", "general_statement")
        if strength not in _VALID_STRENGTH:
            strength = "general_statement"
        conf = induced_confidence(len(cleaned), strength, e.get("multi_paper", False))
        out.append({
            "prereq_slug": a, "target_slug": b, "edge_type": "similarity",
            "evidence": cleaned, "max_strength": strength,
            "confidence": conf, "high_impact": False,
        })
    return out
