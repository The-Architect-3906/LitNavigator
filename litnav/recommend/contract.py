from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Recommendation:
    concept_id: int
    slug: str
    name: str
    score: float
    reason: str
    eligible: bool
