"""Shared survey/review title heuristic for DISCOVER adapters (Fix A)."""
from __future__ import annotations

_REVIEW_CUES = ("survey", "review", "overview", "tutorial",
                "a comprehensive", "systematic literature")


def looks_like_review(title: str) -> bool:
    t = (title or "").lower()
    return any(cue in t for cue in _REVIEW_CUES)
