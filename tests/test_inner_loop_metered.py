"""OW-4 Task 1: inner-loop LLM calls must be routed through the metered router.

Offline (provider=none) the router returns the fallback value unchanged AND writes a
0-cost cost_ledger row. These tests confirm that grade_kp, teach_kp, and reteach_kp
all produce ledger rows after a single grading turn.
"""
from __future__ import annotations

import sqlite3

import pytest

from litnav.storage import repo
from litnav.storage.schema import init_db


def _base_conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "s", topic="t")
    return conn


def _make_concept(conn):
    """Insert a minimal concept + keypoint + chunk so nodes can run."""
    conn.execute(
        "INSERT INTO concepts (id, slug, name, description) VALUES (1, 'test', 'Test', 'desc')"
    )
    conn.execute(
        "INSERT INTO paper_chunks (id, paper_id, text) VALUES ('c1', NULL, 'chunk text')"
    )
    conn.execute(
        "INSERT INTO keypoints (id, concept_id, name, objective, evidence_chunk_id) "
        "VALUES ('kp1', 1, 'KP One', 'understand it', 'c1')"
    )
    conn.execute(
        "INSERT INTO quiz_items (concept_id, question, answer_key, qtype, difficulty, "
        "rubric, expected_keypoints, keypoint_id, bloom_level) "
        "VALUES (1, 'q?', 'answer', 'explain', 1, 'rubric', 'answer', 'kp1', 'recall')"
    )
    conn.commit()


def _grade_state():
    quiz_id = 1  # will be set after _make_concept
    return {
        "session_id": "s",
        "concept_progress": {
            "concept_id": 1,
            "phase": "assessing",
            "keypoints": ["kp1"],
            "taught_idx": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.4, "correct_obs": 0, "last_result": None,
                                       "reteach_count": 0, "strategies_used": []}},
            "misconceptions": {},
        },
        "current_quiz_item": {
            "id": 1,
            "question": "q?",
            "answer_key": "answer",
            "rubric": "rubric",
            "expected_keypoints": "answer",
            "evidence_chunk_id": "c1",
        },
        "pending_answers": ["my answer"],
        "user_answer": "my answer",
        "current_cited_chunks": [],
        "history": [],
    }


def test_grade_kp_writes_metered_cost_ledger_row(monkeypatch):
    """grade_kp_node must write a cost_ledger row with stage='grade' when routed."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    # Re-import after env var is set so the client sees provider=none
    from litnav.nodes import grade_kp

    conn = _base_conn()
    _make_concept(conn)
    state = _grade_state()

    grade_kp.grade_kp_node(state, conn)

    rows = conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE session_id='s' AND stage='grade'"
    ).fetchone()[0]
    assert rows >= 1, f"Expected >= 1 cost_ledger row for stage='grade', got {rows}"


def test_teach_kp_writes_metered_cost_ledger_row(monkeypatch):
    """teach_kp_node must write a cost_ledger row with stage='teach'."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    from litnav.nodes import teach_kp

    conn = _base_conn()
    _make_concept(conn)

    state = {
        "session_id": "s",
        "concept_progress": {
            "concept_id": 1,
            "phase": "teaching",
            "keypoints": ["kp1"],
            "taught_idx": 0,
            "current_keypoint_id": None,
            "current_bloom": None,
            "keypoint_state": {"kp1": {"mastery": 0.3, "correct_obs": 0, "last_result": None,
                                       "reteach_count": 0, "strategies_used": []}},
            "misconceptions": {},
        },
        "history": [],
    }

    teach_kp.teach_kp_node(state, conn)

    rows = conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE session_id='s' AND stage='teach'"
    ).fetchone()[0]
    assert rows >= 1, f"Expected >= 1 cost_ledger row for stage='teach', got {rows}"


def test_reteach_kp_writes_metered_cost_ledger_row(monkeypatch):
    """reteach_kp_node must write a cost_ledger row with stage='reteach'."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    from litnav.nodes import reteach_kp

    conn = _base_conn()
    _make_concept(conn)

    state = {
        "session_id": "s",
        "route_version": 1,
        "concept_progress": {
            "concept_id": 1,
            "phase": "assessing",
            "keypoints": ["kp1"],
            "taught_idx": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.3, "correct_obs": 0, "last_result": "wrong",
                                       "reteach_count": 0, "strategies_used": []}},
            "misconceptions": {},
        },
        "history": [],
    }

    reteach_kp.reteach_kp_node(state, conn)

    rows = conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE session_id='s' AND stage='reteach'"
    ).fetchone()[0]
    assert rows >= 1, f"Expected >= 1 cost_ledger row for stage='reteach', got {rows}"
