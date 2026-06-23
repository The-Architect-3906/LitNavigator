"""DIGEST stage 1 — extract candidate concepts + keypoints from source chunks.

Offline (provider=none): replay the prepared `candidate` (the fixture's baked extraction) so the
pipeline is deterministic at $0. Live: ask a CHEAP-tier model to name the concepts/keypoints grounded
in the chunk text, falling back to the candidate on any malformed field. The LLM never returns
confidence — that is computed downstream by induced_confidence.

All returned dicts are COPIES — offline the router returns the candidate by reference, so mutating in
place would contaminate the shared candidate across calls.
"""
from __future__ import annotations

import sqlite3

from litnav.digest.contract import DigestInput
from litnav.llm import router

_BLOOM = {"recall", "understand", "apply", "analyze", "evaluate", "create"}
_BLOOM_DEFAULT = "recall"


def _valid_concept(c: dict) -> bool:
    return isinstance(c, dict) and isinstance(c.get("slug"), str) and bool(c["slug"].strip())


def extract_concepts(di: DigestInput, *, candidate: dict, session_id: str | None,
                     conn: sqlite3.Connection | None, budget: int | None = None
                     ) -> tuple[list[dict], list[dict]]:
    """Return (concepts, keypoints). `candidate` is the offline replay AND the live fallback.
    Returned dicts are fresh copies (never the candidate's objects)."""
    chunk_blob = "\n---\n".join(ch for s in di.sources for ch in s.chunks)
    prompt = (
        f"Decompose the evidence below (domain: '{di.domain_key}') into a TEACHABLE concept map.\n"
        "Extract 4-8 DISTINCT, specific sub-concepts. Each must be a single precise technical idea that "
        "could be taught and quizzed on its own (e.g. 'chain-of-thought prompting', 'tool invocation', "
        "'observation feedback loop'), NOT one umbrella term for the whole work. "
        "Do NOT return a single concept for the whole paper — break it into its component ideas. "
        "Prefer GENERAL, field-level concepts a learner would recognize across the field; do NOT use "
        "one system's proprietary names or acronyms as concepts (e.g. prefer 'episodic memory' over a "
        "single paper's product name). "
        "Favor concepts that have prerequisite or relatedness links among each other. "
        "Give each a short snake_case slug. Ground every item ONLY in the evidence; do not invent.\n\n"
        "IMPORTANT — each keypoint's `objective` must be a FULL SENTENCE describing what a learner will "
        "understand or be able to do, naming the mechanism or why/how, not just the topic. "
        'Bad: "explain ReAct". Good: "Explain how ReAct interleaves reasoning traces and actions '
        'so that the agent can ground its decisions in real-world observations."\n\n'
        f"Evidence:\n{chunk_blob}\n\n"
        "For each concept, you MAY list the slugs of concepts it directly builds on (its prerequisites), "
        "using ONLY slugs from this same response; omit the field if none.\n"
        'Respond as JSON: {"concepts": [{"slug","name","domain","frontier_flag","builds_on":[]}], '
        '"keypoints": [{"kp_id","concept_slug","name","objective","evidence_chunk_id",'
        '"evidence_quote","bloom_level"}]} '
        'where evidence_quote is a SHORT (≤120 chars) VERBATIM span copied from the evidence '
        'text that directly supports this keypoint (copy the exact words, do not paraphrase).'
    )
    result = router.complete_json(prompt, tier="cheap", stage="digest", fallback=candidate,
                                  session_id=session_id, conn=conn, budget=budget, cache=True)

    raw_concepts = result.get("concepts") if isinstance(result, dict) else None
    if isinstance(raw_concepts, list):
        concepts = [dict(c) for c in raw_concepts if _valid_concept(c)]
    else:
        concepts = []
    if not concepts:                                   # malformed -> fall back wholesale (copied)
        concepts = [dict(c) for c in candidate["concepts"]]
    for c in concepts:
        c.setdefault("domain", di.domain_key)
        c.setdefault("frontier_flag", None)

    slugs = {c["slug"] for c in concepts}
    # Parse builds_on: filter to valid slugs in this response; drop self-refs; default [].
    # Offline candidates without builds_on get [] (no mutation of shared candidate objects).
    for c in concepts:
        raw_bo = c.get("builds_on")
        if isinstance(raw_bo, list):
            c["builds_on"] = [s for s in raw_bo
                               if isinstance(s, str) and s in slugs and s != c["slug"]]
        else:
            c["builds_on"] = []

    raw_kps = result.get("keypoints") if isinstance(result, dict) else None
    keypoints: list[dict] | None = None
    if isinstance(raw_kps, list):
        cand = []
        for k in raw_kps:
            if isinstance(k, dict) and k.get("concept_slug") in slugs and k.get("kp_id") is not None:
                k = dict(k)
                k["kp_id"] = str(k["kp_id"])   # LLM often returns an int id; coerce, don't discard (cf. D1)
                cand.append(k)
        if cand:
            keypoints = cand
    if keypoints is None:
        keypoints = [dict(k) for k in candidate["keypoints"]]
    keypoints = [k for k in keypoints if k.get("concept_slug") in slugs]  # drop orphans
    for k in keypoints:
        if k.get("bloom_level") not in _BLOOM:
            k["bloom_level"] = _BLOOM_DEFAULT
    return concepts, keypoints
