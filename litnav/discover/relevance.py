"""Source-relevance gate: drop off-topic sources after ranking, before full-text fetch.

A14 — *precision*, not just topical adjacency: a cheap LLM scores each source 0-3 for how well it
matches the learner's SPECIFIC goal, and a source in the same broad area but about a DIFFERENT
method/sub-topic (e.g. PBFT when the goal is Raft; QLoRA when the goal is RLHF) is rejected, not just
films/other fields. Never starves digest (keeps >= min_keep, best-scored first). Offline = passthrough.
"""
from __future__ import annotations
import os
import sqlite3

from litnav.discover.contract import Source
from litnav.llm import router

_KEEP_MIN_SCORE = 2     # 3=directly on-goal, 2=substantially, 1=same-area-different (reject), 0=unrelated
_DECLINE_SCORE = 1      # below this = topic-MISMATCH (different domain): never keep, even as fallback


def relevance_gate(
    goal: str,
    sources: list[Source],
    *,
    conn: sqlite3.Connection | None = None,
    session_id: str | None = None,
    budget: int | None = None,
    min_keep: int = 2,
) -> list[Source]:
    """Keep only sources that match the SPECIFIC goal, best-scored first.

    Returns sources scoring >= 2 (ordered by score desc, then original rank). If fewer than
    min_keep clear the bar, falls back to the top min_keep by score (never starves digest).
    Empty input / offline / malformed response → returned unchanged (safe passthrough).
    """
    if not sources:
        return sources
    if os.environ.get("LITNAV_LLM_PROVIDER", "").lower() in ("none", "offline"):
        return sources

    listing = "\n".join(f"{i}: {s.title} — {s.abstract[:300]}" for i, s in enumerate(sources))
    prompt = (
        "A learner wants to study this SPECIFIC goal. First infer the CANONICAL technical sense the "
        "learner most likely means (e.g. 'ReAct' = the LLM reasoning-and-acting agent technique, NOT "
        "psychological reactance or react.js; 'attention' = the deep-learning attention mechanism, NOT "
        "attention in cognitive psychology). Then score how well EACH source's ACTUAL SUBJECT matches "
        "that intended DOMAIN — not just whether the words overlap or the source is authoritative.\n"
        f"GOAL: {goal}\n\n"
        "Scoring (judge topic/domain match, be strict — a high-authority paper in the WRONG domain "
        "scores 0, not 1):\n"
        "  3 = directly and specifically about the goal, in the intended domain\n"
        "  2 = substantially about the goal, in the intended domain\n"
        "  1 = same broad area/domain but a DIFFERENT method / sub-topic than asked (e.g. a different "
        "algorithm in the same family) — NOT what the learner wants\n"
        "  0 = topic MISMATCH: a different field/domain, a homonym in the wrong sense, a film, or an "
        "off-topic page — even if it is highly cited\n\n"
        f"Sources:\n{listing}\n\n"
        'Respond JSON only: {"scores": [{"i": <index>, "score": <0-3>}]}'
    )
    fallback = {"scores": [{"i": i, "score": 2} for i in range(len(sources))]}
    res = router.complete_json(prompt, tier="cheap", stage="discover", fallback=fallback,
                              session_id=session_id, conn=conn, budget=budget)

    # Parse: support the A14 scored format AND the legacy {"relevant_indices": [...]} format.
    score_by_i: dict[int, float] = {i: 0.0 for i in range(len(sources))}
    parsed = False
    if isinstance(res, dict) and isinstance(res.get("scores"), list):
        parsed = True
        for e in res["scores"]:
            if isinstance(e, dict) and isinstance(e.get("i"), int) and 0 <= e["i"] < len(sources):
                try:
                    score_by_i[e["i"]] = float(e.get("score", 0))
                except (TypeError, ValueError):
                    pass
    elif isinstance(res, dict) and isinstance(res.get("relevant_indices"), list):
        parsed = True
        for i in res["relevant_indices"]:
            if isinstance(i, int) and 0 <= i < len(sources):
                score_by_i[i] = 2.0
    if not parsed:
        return sources   # malformed → don't filter

    kept_idx = sorted((i for i, sc in score_by_i.items() if sc >= _KEEP_MIN_SCORE),
                      key=lambda i: (-score_by_i[i], i))
    if len(kept_idx) < min_keep:
        # A6: never STARVE digest — but never feed it a topic-MISMATCH either. The fallback keeps
        # the top min_keep *only among sources that are at least weakly on-topic* (score >= 1, same
        # broad area). When every candidate scores 0 (different domain — the ReAct→reactance bug),
        # nothing clears the bar and we return empty: the caller declines honestly rather than
        # building a confidently-wrong course on a high-authority off-topic paper.
        on_topic = [i for i in range(len(sources)) if score_by_i[i] >= _DECLINE_SCORE]
        kept_idx = sorted(on_topic, key=lambda i: (-score_by_i[i], i))[:min_keep]
    return [sources[i] for i in kept_idx]
