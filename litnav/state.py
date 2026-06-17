from __future__ import annotations

import operator
from typing import Annotated, Dict, List, Literal, Optional, TypedDict


class ConceptState(TypedDict):
    mastery: float
    confidence: float
    n_observations: int
    evidence: List[dict]
    held_misconceptions: List[str]
    tried_strategies: List[str]
    depth: Literal["recall", "apply", "explain"]


class RouteStep(TypedDict):
    step_id: str
    concept_id: int
    paper_id: Optional[int]
    reason: str
    status: str
    confidence: float


class NavState(TypedDict):
    # Identity
    session_id: str
    user_goal: str
    topic: str

    # Concept graph
    concept_dag: Dict[int, List[int]]       # concept_id -> prereq_concept_ids
    all_concept_ids: List[int]
    target_concept_ids: List[int]

    # Route
    route: List[dict]
    route_version: int

    # Current position
    current_concept_id: Optional[int]
    current_evidence: List[dict]
    current_quiz_item: Optional[dict]

    # Inner-loop teaching state (M2)
    current_strategy: Optional[str]         # explanation strategy of the current teach/reteach turn
    current_cited_chunks: List[str]         # chunks cited by the current teach/reteach turn
    used_quiz_ids: Dict[int, List[int]]     # {concept_id: [quiz_item_ids drawn]} — pre/post dedup per concept

    # Literature induction (M3)
    pending_induction: Optional[dict]       # off-skeleton candidate to induce before teaching, or None

    # Answer handling
    user_answer: Optional[str]
    pending_answers: List[str]              # pre-seeded for gate / batch mode

    # Results
    quiz_result: Optional[dict]
    diagnosis: Optional[dict]
    decision: Optional[str]
    rationale: Optional[str]

    # Learner model
    learner_state: dict                     # {concept_id: ConceptState}
    mastery_threshold: float
    reteach_count: dict                     # {concept_id: int}

    # Append-only audit history (LangGraph merges with operator.add)
    history: Annotated[List[dict], operator.add]


# Explanation strategies, tried in order; reteach picks the first not yet used.
RETEACH_STRATEGIES = ["direct", "analogy", "worked_example", "contrast_case", "simpler_decomposition"]


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
