"""Intent classification: a metered cheap-LLM seam with an offline keyword heuristic fallback."""
from __future__ import annotations
import sqlite3
from litnav.discover.contract import INTENTS
from litnav.llm import router

_HEURISTIC = [
    ("crash-course", ("quick", "intro", "introduction", "beginner", "overview", "crash")),
    ("systematic", ("systematic", "thorough", "comprehensive", "survey", "review", "literature")),
    ("cutting-edge", ("cutting-edge", "latest", "state-of-the-art", "sota", "recent", "frontier")),
    ("applied", ("how do i", "how to", "build", "implement", "apply", "practical", "use")),
    ("reference", ("what is", "define", "definition", "reference", "look up")),
]


def _heuristic(goal: str) -> str:
    g = goal.lower()
    for intent, cues in _HEURISTIC:
        if any(cue in g for cue in cues):
            return intent
    return "reference"


def classify(goal_text: str, *, conn: sqlite3.Connection | None, session_id: str | None,
             explicit: str | None = None, budget: int | None = None) -> str:
    """Return an intent in INTENTS. explicit wins; else LLM (cheap) live, heuristic offline/fallback."""
    if explicit in INTENTS:
        return explicit
    fb = _heuristic(goal_text)
    prompt = (
        f"Classify this learning goal into exactly one intent.\nGoal: {goal_text}\n"
        f"Intents: {sorted(INTENTS)}\n"
        'Respond JSON: {"intent": "<one of the intents>"}'
    )
    res = router.complete_json(prompt, tier="cheap", stage="discover", fallback={"intent": fb},
                              session_id=session_id, conn=conn, budget=budget)
    intent = res.get("intent") if isinstance(res, dict) else None
    return intent if intent in INTENTS else fb
