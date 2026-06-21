"""Goal elicitation node (OW-4 §6.3).

Classifies the learner's stated goal into one of three types:
  mastery    — deep understanding ("master", "deeply understand", "thoroughly")
  functional — practical usage  ("build", "implement", "how to", "be able to")
  survey     — broad overview   ("overview", "quick", "intro", "survey", "gist")

The goal_type sets the Bloom ceiling (via bloom_ceiling_for) and pacing for the
orient → teach_kp → assess_next → grade_kp → route loop.

This node is idempotent: if state["goal_type"] is already set it returns
immediately without re-classifying or re-persisting.
"""
from __future__ import annotations

import re
import sqlite3

from litnav.llm import router, lang
from litnav.state import bloom_ceiling_for
from litnav.storage import openworld_repo

_VALID_TYPES = {"mastery", "functional", "survey"}

# ── keyword → goal_type heuristic ────────────────────────────────────────────
_MASTERY_RE = re.compile(
    r"\b(master|mastery|deeply|deep(?:ly)?\s+understand|thoroughly|expert|rigorous)\b",
    re.IGNORECASE,
)
_FUNCTIONAL_RE = re.compile(
    r"\b(build|implement|how\s+to|be\s+able\s+to|use|apply|deploy|create|develop|practise|practice)\b",
    re.IGNORECASE,
)
_SURVEY_RE = re.compile(
    r"\b(overview|quick|intro(?:duction)?|survey|gist|summary|just\s+a|high.level|briefly)\b",
    re.IGNORECASE,
)


def _heuristic(goal_text: str) -> str:
    """Keyword heuristic — survey wins over functional wins over mastery (most to least defensive)."""
    if _SURVEY_RE.search(goal_text):
        return "survey"
    if _FUNCTIONAL_RE.search(goal_text):
        return "functional"
    if _MASTERY_RE.search(goal_text):
        return "mastery"
    return "mastery"  # default: treat unknown goals as mastery (preserve existing behavior)


# ── public classify_goal ──────────────────────────────────────────────────────

def classify_goal(
    goal_text: str,
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None = None,
) -> str:
    """Classify goal_text into goal_type.

    Uses heuristic as the primary signal AND as the fallback.  The LLM call
    (tier="cheap") may improve accuracy live; offline (provider=none) the
    client returns the fallback dict directly so the heuristic always wins.
    """
    heuristic = _heuristic(goal_text)

    result = router.complete_json(
        f"Classify this learner goal into EXACTLY one of: mastery, functional, survey.\n"
        f"- mastery: wants deep understanding, expertise, thorough comprehension\n"
        f"- functional: wants to build, implement, or use the knowledge practically\n"
        f"- survey: wants a quick overview, broad introduction, or high-level gist\n\n"
        f'Respond with JSON only: {{"goal_type": "<mastery|functional|survey>"}}\n\n'
        f'Learner goal: "{goal_text}"',
        tier="cheap",
        stage="goal_elicit",
        fallback={"goal_type": heuristic},
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    goal_type = result.get("goal_type", heuristic) if result else heuristic
    if goal_type not in _VALID_TYPES:
        goal_type = heuristic

    return goal_type


# ── graph node ────────────────────────────────────────────────────────────────

def goal_elicit_node(state: dict, conn: sqlite3.Connection) -> dict:
    """LangGraph node: classify goal and persist; idempotent if goal already set.

    Returns a dict merged into NavState with:
      goal_type     — "mastery" | "functional" | "survey"
      bloom_ceiling — Bloom level cap derived from goal_type
      (history entry appended, plus rationale on first classification)
    """
    existing_type = state.get("goal_type")
    if existing_type and existing_type in _VALID_TYPES:
        # Already classified — just ensure bloom_ceiling is present (idempotent path)
        return {
            "goal_type": existing_type,
            "bloom_ceiling": bloom_ceiling_for(existing_type),
        }

    goal_text: str = state.get("goal_text") or state.get("topic") or ""
    session_id: str = state["session_id"]

    goal_type = classify_goal(goal_text, conn=conn, session_id=session_id)
    ceiling = bloom_ceiling_for(goal_type)
    target_language = lang.detect_language(goal_text, conn=conn, session_id=session_id)

    openworld_repo.set_goal(
        conn,
        session_id,
        goal_text,
        goal_type,
        list(state.get("target_concept_ids") or []),
    )

    return {
        "goal_type": goal_type,
        "goal_text": goal_text,
        "bloom_ceiling": ceiling,
        "target_language": target_language,
        "rationale": f"Goal elicitation: '{goal_text[:80]}' → {goal_type} (bloom_ceiling={ceiling})",
        "history": [{"event": "goal_elicit", "goal_type": goal_type, "bloom_ceiling": ceiling}],
    }
