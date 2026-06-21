"""Tests for A12 (prereq-detour on keypoint path) and A13 (mid-session goal pivot).

A12: assess_decider returns "diagnose" when reteach is exhausted AND the concept has
     an unmastered prereq that is NOT already in the route.

A13: repivot_goal returns a correct state patch for a new goal text (offline-safe).
"""
from __future__ import annotations

import sqlite3

from litnav.nodes.grade_kp import assess_decider
from litnav.storage.schema import init_db


def _mem_conn() -> sqlite3.Connection:
    """In-memory connection with full schema (needed for cost metering)."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


# ─── helpers ──────────────────────────────────────────────────────────────────

def _exhausted_state(
    *,
    concept_id: int = 10,
    prereq_ids: list[int] | None = None,
    prereq_mastery: float = 0.0,   # below threshold by default → unmastered
    prereq_in_route: bool = False,
    mastery: float = 0.3,
    correct_obs: int = 0,
) -> dict:
    """Build a minimal state that hits the reteach-exhausted branch."""
    dag: dict[int, list[int]] = {}
    if prereq_ids:
        dag[concept_id] = prereq_ids

    learner_state: dict = {}
    for pid in (prereq_ids or []):
        learner_state[pid] = {"mastery": prereq_mastery}

    route: list[dict] = [{"concept_id": concept_id, "step_id": "r-001", "status": "pending"}]
    if prereq_in_route and prereq_ids:
        for pid in prereq_ids:
            route.append({"concept_id": pid, "step_id": f"r-prereq-{pid}", "status": "pending"})

    return {
        "session_id": "test",
        "concept_dag": dag,
        "learner_state": learner_state,
        "mastery_threshold": 0.75,
        "route": route,
        "route_version": 1,
        "bloom_ceiling": "application",
        "concept_progress": {
            "concept_id": concept_id,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {
                "kp1": {
                    "mastery": mastery,
                    "correct_obs": correct_obs,
                    "last_result": "wrong",
                    "reteach_count": 2,   # exhausted
                },
            },
        },
    }


def _correct_state(bloom: str, ceiling: str, mastery: float, correct_obs: int = 3) -> dict:
    """Build a state for the happy-path (correct answer) tests."""
    return {
        "session_id": "s",
        "route": [],
        "route_version": 1,
        "bloom_ceiling": ceiling,
        "concept_dag": {},
        "learner_state": {},
        "mastery_threshold": 0.75,
        "concept_progress": {
            "concept_id": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": bloom,
            "keypoint_state": {
                "kp1": {
                    "mastery": mastery,
                    "correct_obs": correct_obs,
                    "last_result": "correct",
                    "reteach_count": 0,
                },
            },
        },
    }


# ─── A12 tests ────────────────────────────────────────────────────────────────

def test_a12_fires_when_unmastered_prereq_not_in_route():
    """Exhausted reteaches + unmastered prereq not in route → diagnose (detour)."""
    state = _exhausted_state(prereq_ids=[5], prereq_mastery=0.1, prereq_in_route=False)
    assert assess_decider(state) == "diagnose"


def test_a12_guard_prereq_already_in_route_no_infinite_detour():
    """Prereq is already in the route → skip detour, concede (advance_kp)."""
    state = _exhausted_state(prereq_ids=[5], prereq_mastery=0.1, prereq_in_route=True)
    assert assess_decider(state) == "advance_kp"


def test_a12_no_prereqs_concedes():
    """No prereqs at all → concede (advance_kp)."""
    state = _exhausted_state(prereq_ids=None)
    assert assess_decider(state) == "advance_kp"


def test_a12_prereq_already_mastered_concedes():
    """Prereq exists but is already mastered (above threshold) → concede."""
    state = _exhausted_state(prereq_ids=[5], prereq_mastery=0.9, prereq_in_route=False)
    assert assess_decider(state) == "advance_kp"


# ─── Happy path intact ─────────────────────────────────────────────────────────

def test_happy_correct_below_ceiling_assess_next():
    """Correct answer below Bloom ceiling → assess_next (bloom upgrade)."""
    state = _correct_state("recall", "application", mastery=0.9, correct_obs=3)
    assert assess_decider(state) == "assess_next"


def test_happy_correct_at_ceiling_mastered_advance_kp():
    """Correct at ceiling + mastered → advance_kp."""
    state = _correct_state("application", "application", mastery=0.9, correct_obs=3)
    assert assess_decider(state) == "advance_kp"


# ─── A13 tests ────────────────────────────────────────────────────────────────

def test_a13_repivot_goal_returns_correct_fields():
    """repivot_goal returns goal_type, bloom_ceiling, goal_text, target_language."""
    from litnav.nodes.goal_elicit import repivot_goal

    conn = _mem_conn()
    state = {"session_id": "test-pivot"}

    # "overview" → survey goal
    result = repivot_goal(state, "I just want a quick overview of this topic", conn=conn)
    assert "goal_type" in result
    assert "bloom_ceiling" in result
    assert result["goal_text"] == "I just want a quick overview of this topic"
    assert result["goal_type"] == "survey"
    assert result["bloom_ceiling"] == "comprehension"
    assert "target_language" in result


def test_a13_repivot_mastery_goal():
    """repivot_goal for a mastery goal returns application ceiling."""
    from litnav.nodes.goal_elicit import repivot_goal

    conn = _mem_conn()
    state = {"session_id": "test-pivot2"}

    result = repivot_goal(state, "I want to master and deeply understand this", conn=conn)
    assert result["goal_type"] == "mastery"
    assert result["bloom_ceiling"] == "application"
    assert result["goal_text"] == "I want to master and deeply understand this"


def test_a13_repivot_functional_goal():
    """repivot_goal for a functional/build goal returns application ceiling."""
    from litnav.nodes.goal_elicit import repivot_goal

    conn = _mem_conn()
    state = {"session_id": "test-pivot3"}

    result = repivot_goal(state, "I want to implement and build a system using this", conn=conn)
    assert result["goal_type"] == "functional"
    assert result["bloom_ceiling"] == "application"
