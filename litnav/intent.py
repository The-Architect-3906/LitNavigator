"""Intent / audience modes (M4).

The same engine re-scopes to the learner's *purpose*. An intent maps onto existing
NavState dimensions (no new subsystem): which concepts are targets, the mastery bar,
the teaching depth, and whether contested/open concepts are surfaced first.
"""
from __future__ import annotations

from typing import Optional

INTENTS = {
    "researcher": {
        "label": "Researcher entering the field",
        "mastery_threshold": 0.8,            # "can build and critique it"
        "depth": "explain",                  # full explanations
        "frontier_first": False,             # normal prerequisite order
        # the whole chain + methods + open problems
        "targets": ["react", "tool_use", "reflection", "agent_memory",
                    "skill_learning", "multi_agent", "agent_taxonomy"],
    },
    "journalist": {
        "label": "Journalist prepping an interview",
        "mastery_threshold": 0.6,            # "can hold the conversation"
        "depth": "recall",                   # brief orientation
        "frontier_first": True,              # lead with where the debate is
        # a high-level subset: the map, the core idea, and the live controversy
        "targets": ["agent_taxonomy", "react", "multi_agent"],
    },
}

DEFAULT_INTENT = None  # no intent -> use explicit target_concept_ids + given threshold


def resolve(intent: Optional[str]) -> Optional[dict]:
    if intent is None:
        return None
    if intent not in INTENTS:
        raise ValueError(f"unknown intent {intent!r}; choose from {sorted(INTENTS)}")
    return INTENTS[intent]


def threshold_for(intent: Optional[str], default: float) -> float:
    cfg = resolve(intent)
    return cfg["mastery_threshold"] if cfg else default
