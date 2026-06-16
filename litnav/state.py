from __future__ import annotations

from typing import Literal, TypedDict


class ConceptState(TypedDict):
    mastery: float
    confidence: float
    n_observations: int
    evidence: list[dict]
    held_misconceptions: list[str]
    tried_strategies: list[str]
    depth: Literal["recall", "apply", "explain"]


class RouteStep(TypedDict):
    step_id: str
    concept_id: int
    paper_id: int | None
    reason: str
    status: str
    confidence: float


class NavState(TypedDict):
    session_id: str
    user_goal: str
    concept_dag: dict[int, list[int]]       # concept_id -> list of prereq concept_ids
    learner_state: dict[int, ConceptState]
    route: list[RouteStep]
    route_version: int
    current_concept_id: int | None
    current_evidence: list[dict]
    quiz_result: dict | None
    diagnosis: dict | None
    decision: str | None
    rationale: str | None
    mastery_threshold: float
    reteach_count: dict[int, int]
    history: list[dict]


def initial_concept_state() -> ConceptState:
    return {
        "mastery": 0.4,
        "confidence": 0.0,
        "n_observations": 0,
        "evidence": [],
        "held_misconceptions": [],
        "tried_strategies": [],
        "depth": "recall",
    }


def bkt_update(p: float, correct: bool, taught: bool) -> float:
    slip = 0.10
    guess = 0.20
    transit = 0.30
    if correct:
        post = p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)
    else:
        post = p * slip / (p * slip + (1 - p) * (1 - guess))
    return post + (1 - post) * transit if taught else post


def confidence_update(n_observations: int) -> float:
    return round(1 - 0.6**n_observations, 2)
