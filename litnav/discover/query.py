"""Multilingual goal -> English academic search query normalization.

Cheap-LLM seam with offline passthrough (mirrors intent.py style).
"""
from __future__ import annotations
import os
import sqlite3

from litnav.llm import router

_PROMPT_TMPL = (
    "Rewrite this learning goal as a concise English academic search query (3-8 keywords). "
    "Translate to English if the goal is in another language. "
    "Drop filler like 'I want to deeply master'. Keep the core topic + qualifiers.\n"
    "Goal: {goal_text}\n"
    'Respond JSON only: {{"query": "..."}}'
)

_REFINE_PROMPT_TMPL = (
    "A learner's goal is: {goal_text}\n\n"
    "A search for this goal returned {found_desc}.\n"
    "Propose 2-3 BROADER or DECOMPOSED English academic search queries that would find "
    "foundational papers and overviews on the underlying concepts. "
    "Each query should be 3-8 keywords. Avoid repeating the same query.\n"
    'Respond JSON only: {{"queries": ["...", "...", "..."]}}'
)


def to_search_query(
    goal_text: str,
    *,
    conn: sqlite3.Connection | None = None,
    session_id: str | None = None,
    budget: int | None = None,
) -> str:
    """Return an English search query for goal_text.

    Offline/none provider: returns goal_text unchanged (deterministic, no LLM call).
    Live: asks a cheap LLM to rewrite/translate; falls back to goal_text on blank/error.
    """
    if os.environ.get("LITNAV_LLM_PROVIDER", "").lower() in ("none", "offline"):
        return goal_text

    prompt = _PROMPT_TMPL.format(goal_text=goal_text)
    res = router.complete_json(
        prompt,
        tier="cheap",
        stage="discover",
        fallback={"query": goal_text},
        session_id=session_id,
        conn=conn,
        budget=budget,
    )
    qy = res.get("query") if isinstance(res, dict) else None
    if isinstance(qy, str) and qy.strip():
        return qy.strip()
    return goal_text


def refine_queries(
    goal_text: str,
    prior_titles: list[str],
    intent: str | None,
    *,
    conn: sqlite3.Connection | None = None,
    session_id: str | None = None,
    budget: int | None = None,
) -> list[str]:
    """Given a goal and round-1 result titles, return 2-3 broader/decomposed search queries.

    Offline/none provider: returns [] (so DISCOVER stays single-round and deterministic offline).
    Live: asks a cheap LLM to propose broader or decomposed queries; falls back to [] on
    blank/error. De-dupes returned queries against each other; drops blanks; caps at 3.
    """
    if os.environ.get("LITNAV_LLM_PROVIDER", "").lower() in ("none", "offline"):
        return []

    if prior_titles:
        found_desc = f"only {len(prior_titles)} result(s): {', '.join(prior_titles[:5])}"
    else:
        found_desc = "almost nothing"

    prompt = _REFINE_PROMPT_TMPL.format(goal_text=goal_text, found_desc=found_desc)
    try:
        res = router.complete_json(
            prompt,
            tier="cheap",
            stage="discover",
            fallback={"queries": []},
            session_id=session_id,
            conn=conn,
            budget=budget,
        )
    except Exception:
        return []

    raw = res.get("queries") if isinstance(res, dict) else None
    if not isinstance(raw, list):
        return []

    # Clean: drop blanks, dedup, cap at 3
    seen: set[str] = set()
    result: list[str] = []
    for q in raw:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        result.append(q)
        if len(result) >= 3:
            break
    return result
