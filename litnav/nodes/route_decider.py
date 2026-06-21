"""Concept-level advance gate: dual-threshold advance (mastery + confidence).

Fixes the '1 observation → advance' bug: correct_obs must reach ≥ 2 before
confidence clears KP_CONF_THRESHOLD (0.5), so the learner needs to demonstrate
understanding on at least two independent questions before advancing.
"""
from __future__ import annotations

import sqlite3

from litnav.state import KP_CONF_THRESHOLD, KP_MASTERY_THRESHOLD, NavState, kp_confidence
from litnav.storage import repo


def _concept_mastery(kp_states: dict) -> float:
    if not kp_states:
        return 0.0
    return round(sum(s.get("mastery", 0.3) for s in kp_states.values()) / len(kp_states), 3)


def _concept_confidence(kp_states: dict) -> float:
    total_correct = sum(s.get("correct_obs", 0) for s in kp_states.values())
    return kp_confidence(total_correct)


def route_decider_node(state: NavState) -> str:
    """Return 'advance' | 'hold' based on dual-threshold logic.

    Misconceptions within TEACH/ASSESS are concept-internal (flagged by quiz items).
    They do NOT trigger 'replan' here — replan is only for the legacy tutor_router
    path that calls diagnose() to detect missing prerequisites.
    After reteach exhaustion, assess_decider maps 'hold' to advance_kp (concede).
    """
    cp = state["concept_progress"]
    kp_states = cp["keypoint_state"]

    m = _concept_mastery(kp_states)
    c = _concept_confidence(kp_states)

    if m >= KP_MASTERY_THRESHOLD and c >= KP_CONF_THRESHOLD:
        return "advance"

    return "hold"


def advance_kp_node(state: NavState, conn: sqlite3.Connection) -> dict:
    """Leave the concept and move on — honestly distinguishing a true ADVANCE (thresholds met)
    from a CONCEDE (reteach exhausted, thresholds not met). assess_decider routes both cases
    here, so this node must not claim mastery it didn't reach."""
    cp = state["concept_progress"]
    concept_id = cp["concept_id"]
    kp_states = cp["keypoint_state"]

    m = _concept_mastery(kp_states)
    c = _concept_confidence(kp_states)
    mastered = m >= KP_MASTERY_THRESHOLD and c >= KP_CONF_THRESHOLD
    decision = "advance" if mastered else "concede"
    new_status = "done" if mastered else "conceded"

    route = [dict(s) for s in state["route"]]
    for step in route:
        if step["concept_id"] == concept_id and step.get("status") == "pending":
            step["status"] = new_status
            repo.update_route_step_status(
                conn, state["session_id"], state["route_version"],
                step["step_id"], new_status,
            )
            break

    if mastered:
        rationale = (
            f"ADVANCE concept {concept_id}: mastery={m:.3f}≥{KP_MASTERY_THRESHOLD}, "
            f"confidence={c:.3f}≥{KP_CONF_THRESHOLD} (≥2 correct observations). Concept mastered."
        )
    else:
        rationale = (
            f"CONCEDE concept {concept_id}: reteach exhausted and thresholds not met "
            f"(mastery={m:.3f}<{KP_MASTERY_THRESHOLD} or confidence={c:.3f}<{KP_CONF_THRESHOLD}). "
            f"Marking not-yet-mastered and moving on rather than looping."
        )
    repo.record_decision(
        conn, state["session_id"], state["route_version"],
        "route_decider", decision, rationale,
        state_snapshot={"concept_id": concept_id, "mastery": m, "confidence": c},
    )

    return {
        "route": route,
        "concept_progress": None,   # clear so next concept starts fresh (P2 fix)
        "current_quiz_item": None,  # no active question after concept advance
        # spaced retrieval: record that this concept was just seen (at the current step)
        "concept_last_seen": {**(state.get("concept_last_seen") or {}), concept_id: state.get("step", 0)},
        "decision": decision,
        "rationale": rationale,
        "history": [{"event": decision, "concept_id": concept_id, "mastery": m, "confidence": c}],
    }
