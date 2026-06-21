from __future__ import annotations

import operator
from typing import Annotated, Dict, List, Literal, Optional, TypedDict

BLOOM_LADDER = ["recall", "comprehension", "application"]


def bloom_ceiling_for(goal_type: str) -> str:
    """Return the Bloom-ladder ceiling for a learner goal type.

    survey     → comprehension (2nd level — broad recognition, no deep application)
    functional → application   (top — must be able to USE the knowledge)
    mastery    → application   (top — same ceiling; mastery affects pacing, not ceiling)
    Unknown types default to the top level so existing flows are unaffected.
    """
    ceilings = {
        "survey":     BLOOM_LADDER[1],   # "comprehension"
        "functional": BLOOM_LADDER[-1],  # "application"
        "mastery":    BLOOM_LADDER[-1],  # "application"
    }
    return ceilings.get(goal_type, BLOOM_LADDER[-1])
TEACH_STRATEGIES = ["direct", "analogy", "contrast", "worked_example"]
KP_MASTERY_THRESHOLD = 0.75
KP_CONF_THRESHOLD = 0.50    # requires correct_obs >= 2 to pass


class KeyPointState(TypedDict):
    keypoint_id: str
    mastery: float            # [0,1]
    correct_obs: int          # independent correct observations (drives confidence)
    last_result: Optional[str]          # "correct" | "wrong" | None
    reteach_count: int
    strategies_used: List[str]


class ConceptProgress(TypedDict):
    concept_id: int
    phase: str                          # "teaching" | "assessing" | "done"
    keypoints: List[str]                # ordered keypoint ids
    taught_idx: int                     # how many keypoints have been taught
    current_keypoint_id: Optional[str]
    current_bloom: Optional[str]        # recall | comprehension | application
    keypoint_state: Dict[str, KeyPointState]
    misconceptions: Dict[str, bool]     # misconception_id -> still held


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
    teach_token_cost: int                   # LLM tokens spent generating the current teach turn (0 offline)
    used_quiz_ids: Dict[int, List[int]]     # {concept_id: [quiz_item_ids drawn]} — pre/post dedup per concept

    # Literature induction (M3)
    pending_induction: Optional[dict]       # off-skeleton candidate to induce before teaching, or None

    # Intent / audience mode (M4)
    intent: Optional[str]                   # 'researcher' | 'journalist' | None
    teach_depth: Optional[str]              # explanation depth set by the intent ('recall'|'explain'|'apply')

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

    # Per-keypoint TEACH/ASSESS progress (None for concepts without keypoints)
    concept_progress: Optional[ConceptProgress]

    # ORIENT phase: True once the roadmap overview has been shown for this session
    orient_done: Optional[bool]

    # Goal elicitation (OW-4): set once at the start of the session
    goal_type: Optional[str]       # "mastery" | "functional" | "survey"
    goal_text: Optional[str]       # raw learner goal text
    bloom_ceiling: Optional[str]   # Bloom level cap derived from goal_type
    target_language: Optional[str] # output language inferred from goal text (e.g. "Chinese")

    # Conversation intent set by the dispatcher for the current turn
    # "lost" → handle_lost node; None → normal flow
    user_intent: Optional[str]

    # Spaced retrieval (in-session): turn counter, per-concept last-seen step, slip flags
    step: int
    concept_last_seen: dict
    needs_review: list

    # Append-only audit history (LangGraph merges with operator.add)
    history: Annotated[List[dict], operator.add]


# Explanation strategies, tried in order; reteach picks the first not yet used.
RETEACH_STRATEGIES = ["direct", "analogy", "worked_example", "contrast_case", "simpler_decomposition"]


def kp_confidence(correct_obs: int) -> float:
    """0 obs→0, 1 obs→0.30 (below threshold), 2 obs→0.60 (passes), saturates at 1.0."""
    return round(min(1.0, 0.30 * correct_obs), 3)


def kp_bump(mastery: float, bloom: str, correct: bool) -> float:
    """Mastery update per keypoint: correct answers converge faster at higher bloom."""
    gain = {"recall": 0.25, "comprehension": 0.40, "application": 0.55}.get(bloom, 0.25)
    if correct:
        return round(mastery + (1 - mastery) * gain, 3)
    return round(max(0.0, mastery - 0.20), 3)


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
