"""Tests for glass-box consistency cleanups (B11, B15, B16, B18).

All run offline (provider=none, deterministic fallback), CI-safe.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from litnav.storage.schema import init_db
from litnav.storage import repo


# ── Shared seed helpers ────────────────────────────────────────────────────────

def _kp_conn():
    """In-memory DB seeded for the keypoint (ORIENT→TEACH→ASSESS) path."""
    from litnav.storage.seed import seed_demo_data
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m3.json")
    return conn


def _legacy_conn():
    """In-memory DB seeded for the legacy (check/grade/advance) path."""
    from litnav.storage.seed import seed_demo_data
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m2.json")
    return conn


def _ckpt():
    return sqlite3.connect(":memory:", check_same_thread=False)


# ── B11: stale decision cleared when moving to the next concept ────────────────

def test_b11_decision_cleared_on_concept_transition():
    """select_next_node must clear decision/rationale so the next concept starts fresh."""
    from litnav.nodes.select_next import select_next_node

    # Simulate state after a concede decision — decision is set from the previous concept.
    state = {
        "route": [
            {"concept_id": 1, "status": "conceded", "step_id": "r1"},
            {"concept_id": 2, "status": "pending",  "step_id": "r2"},
        ],
        "decision": "concede",
        "rationale": "reteach exhausted",
    }
    out = select_next_node(state)
    assert out["current_concept_id"] == 2
    assert out["decision"] is None, "stale decision must be cleared (B11)"
    assert out["rationale"] is None, "stale rationale must be cleared (B11)"


def test_b11_decision_not_cleared_on_end_of_route():
    """When no pending steps remain, select_next_node signals __end__ — no concept_id set."""
    from litnav.nodes.select_next import select_next_node

    state = {
        "route": [{"concept_id": 1, "status": "done", "step_id": "r1"}],
        "decision": "advance",
        "rationale": "concept mastered",
    }
    out = select_next_node(state)
    # Route finished — only current_concept_id=None is returned; decision not touched
    assert out["current_concept_id"] is None
    # decision and rationale should be cleared here too (route done)
    assert out.get("decision") is None


# ── B15: handle_lost writes a decisions row ────────────────────────────────────

def test_b15_handle_lost_records_decision_keypoint_path():
    """handle_lost (ASSESS path) must write a 'lost' decisions row visible in the glass box."""
    from litnav.nodes.handle_lost import handle_lost_node

    conn = _kp_conn()
    repo.create_session(conn, "s-b15a", "test")
    repo.create_keypoint(conn, "kp1", 1, "ReAct loop", "understand the loop")

    state = {
        "session_id": "s-b15a",
        "route_version": 1,
        "concept_progress": {
            "concept_id": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": "comprehension",
            "keypoint_state": {
                "kp1": {"mastery": 0.4, "correct_obs": 0, "strategies_used": []}
            },
            "misconceptions": {},
        },
        "current_evidence": [],
        "user_intent": "lost",
    }
    handle_lost_node(state, conn)

    rows = conn.execute(
        "SELECT decision, from_node FROM decisions WHERE session_id='s-b15a'"
    ).fetchall()
    assert rows, "handle_lost must write at least one decisions row (B15)"
    assert any(r[0] == "lost" for r in rows), f"expected decision='lost', got {rows}"
    assert any(r[1] == "handle_lost" for r in rows)


def test_b15_handle_lost_records_decision_legacy_path():
    """handle_lost (legacy concept path) must also write a decisions row."""
    from litnav.nodes.handle_lost import handle_lost_node

    conn = _legacy_conn()
    repo.create_session(conn, "s-b15b", "test")

    state = {
        "session_id": "s-b15b",
        "route_version": 1,
        "concept_progress": None,   # legacy path
        "current_concept_id": 1,
        "current_evidence": [],
        "user_intent": "lost",
    }
    handle_lost_node(state, conn)

    rows = conn.execute(
        "SELECT decision FROM decisions WHERE session_id='s-b15b'"
    ).fetchall()
    assert rows, "handle_lost (legacy) must write a decisions row (B15)"
    assert rows[0][0] == "lost"


# ── B16: no empty question bubble on route completion ─────────────────────────

def test_b16_no_empty_question_bubble_on_completion(monkeypatch):
    """On route completion, _terminal_events must not emit a question event with empty text."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from litnav.ui.interactive import TutorSession

    conn = _kp_conn()
    ts = TutorSession(conn, _ckpt(), str(uuid.uuid4()))
    ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)

    # Drive to completion: give enough correct answers to finish or exhaust reteaches.
    CORRECT = "thought, action, observation"
    for _ in range(8):
        cur = ts.current()
        if cur.get("done"):
            break
        ts.answer(CORRECT)

    events = ts._terminal_events()

    # There must be no question event with empty text
    empty_q = [e for e in events if e.get("type") == "question" and not e.get("text")]
    assert not empty_q, f"B16: empty question bubble(s) emitted on completion: {empty_q}"

    # If done, there must be a completion event
    cur = ts.current()
    if cur.get("done"):
        comp = [e for e in events if e.get("type") == "completion"]
        assert comp, "B16: no completion event emitted when route is done"
        assert comp[0]["text"], "B16: completion event has empty text"


# ── B18: session.status set to 'done' on completion ──────────────────────────

def test_b18_session_status_becomes_done_on_completion(monkeypatch):
    """Session status must flip from 'active' to 'done' once the route finishes."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from litnav.ui.interactive import TutorSession

    conn = _kp_conn()
    sid = str(uuid.uuid4())
    ts = TutorSession(conn, _ckpt(), sid)
    ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)

    # Before completion the session should be 'active'
    status = conn.execute("SELECT status FROM sessions WHERE id=?", (sid,)).fetchone()
    assert status is not None, "session row must exist"
    assert status[0] == "active"

    CORRECT = "thought, action, observation"
    for _ in range(8):
        cur = ts.current()
        if cur.get("done"):
            break
        ts.answer(CORRECT)

    # Trigger _terminal_events to fire the complete_session call
    ts._terminal_events()

    cur = ts.current()
    if cur.get("done"):
        status = conn.execute("SELECT status FROM sessions WHERE id=?", (sid,)).fetchone()
        assert status[0] == "done", f"B18: session.status should be 'done', got {status[0]!r}"


def test_b18_complete_session_helper_is_idempotent():
    """complete_session can be called multiple times without error."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "s-idem", "t")
    repo.complete_session(conn, "s-idem")
    repo.complete_session(conn, "s-idem")  # second call must not raise
    row = conn.execute("SELECT status FROM sessions WHERE id='s-idem'").fetchone()
    assert row[0] == "done"
