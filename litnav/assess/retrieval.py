"""Pure helpers for in-session spaced retrieval (no I/O). Turn-based 'due', low-stakes reinforcement.
Distinct from kp_bump (first-learning): retrieval reinforcement is gentler. Spec: 2026-06-22-spaced-retrieval."""
from __future__ import annotations

_REINFORCE_GAIN = 0.15
_FORGET_NUDGE = 0.10


def is_due(last_seen_step: int | None, current_step: int, k: int = 2) -> bool:
    if last_seen_step is None:
        return False
    return (current_step - last_seen_step) >= k


def predicted_recall(mastery: float) -> float:
    return round(max(0.0, min(float(mastery), 1.0)), 4)


def reinforce(mastery: float, correct: bool) -> float:
    if correct:
        return round(mastery + (1.0 - mastery) * _REINFORCE_GAIN, 4)
    return round(max(0.0, mastery - _FORGET_NUDGE), 4)
