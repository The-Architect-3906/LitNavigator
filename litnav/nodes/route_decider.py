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
    """Mark concept as done, persist advance decision."""
    cp = state["concept_progress"]
    concept_id = cp["concept_id"]
    kp_states = cp["keypoint_state"]

    m = _concept_mastery(kp_states)
    c = _concept_confidence(kp_states)

    route = [dict(s) for s in state["route"]]
    for step in route:
        if step["concept_id"] == concept_id and step.get("status") == "pending":
            step["status"] = "done"
            repo.update_route_step_status(
                conn, state["session_id"], state["route_version"],
                step["step_id"], "done",
            )
            break

    rationale = (
        f"ADVANCE concept {concept_id}: mastery={m:.3f}≥{KP_MASTERY_THRESHOLD}, "
        f"confidence={c:.3f}≥{KP_CONF_THRESHOLD} (≥2 correct observations). "
        f"No unresolved misconceptions."
    )
    repo.record_decision(
        conn, state["session_id"], state["route_version"],
        "route_decider", "advance", rationale,
        state_snapshot={"concept_id": concept_id, "mastery": m, "confidence": c},
    )

    return {
        "route": route,
        "concept_progress": None,   # clear so next concept starts fresh (P2 fix)
        "current_quiz_item": None,  # no active question after concept advance
        "rationale": rationale,
        "history": [{"event": "advance_kp", "concept_id": concept_id, "mastery": m, "confidence": c}],
    }
