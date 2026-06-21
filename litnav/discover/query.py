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
