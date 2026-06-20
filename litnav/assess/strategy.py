"""Deterministic teach-strategy policy: goal_type × expertise × KT mastery -> strategy label.
No LLM — a cheap policy the teach/reteach nodes read (spec §6.3)."""
from __future__ import annotations


def choose_strategy(goal_type: str | None, expertise: str | None, mastery: float) -> str:
    """Return a teaching strategy label based on learner goal, expertise, and KT mastery.

    Rules (evaluated top-to-bottom):
      1. expert learner           → "concise"  (respect prior knowledge)
      2. survey goal              → "overview" (breadth over depth)
      3. low mastery  (< 0.35)    → "worked_example"
      4. mid mastery  (0.35–0.7)  → "analogy"
      5. high mastery (≥ 0.7)     → "direct"
    """
    if (expertise or "novice") == "expert":
        return "concise"
    if (goal_type or "mastery") == "survey":
        return "overview"
    if mastery < 0.35:
        return "worked_example"
    if mastery < 0.7:
        return "analogy"
    return "direct"
