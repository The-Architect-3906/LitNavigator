"""Regression gate for the keypoint (ORIENT->TEACH->ASSESS) flow.

These cover the bugs that shipped because the milestone gates only exercise the legacy path:
  BUG 1 — keypoint mastery must be persisted to learner_state (not left in graph state).
  BUG 2 — advance_kp must distinguish a true ADVANCE from a CONCEDE (no false "mastered").
  BUG 5 — grade_kp must detect a misconception from the ANSWER, not only the quiz's static field.
  BUG 3b — the posed question must carry its bloom level.
All run offline (provider=none → deterministic fallback grader), so they are CI-safe.
"""
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes.grade_kp import grade_kp_node
from litnav.nodes.route_decider import advance_kp_node

ANSWER_KEY = "thought, action, observation"


def _seed():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "topic")
    repo.create_concept(c, 1, "react", "ReAct")
    repo.upsert_learner_state(c, "s", 1, mastery=0.4, confidence=0.0, n_observations=0)
    qid = repo.create_quiz_item(c, 1, "What three steps?", ANSWER_KEY,
                                keypoint_id="kp1", bloom_level="recall")
    repo.record_induced_misconception(
        c, "react_is_just_cot", 1, "ReAct is just chain-of-thought",
        "ReAct grounds reasoning in actions and observations", 0.7, None,
        detect_hint="chain of thought|just.*cot")
    return c, qid


def _grade_state(qid, answer):
    return {
        "session_id": "s", "route_version": 1, "current_cited_chunks": [],
        "pending_answers": [answer], "user_answer": None,
        "concept_progress": {
            "concept_id": 1, "current_keypoint_id": "kp1", "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.3, "correct_obs": 0}}, "misconceptions": {},
        },
        "current_quiz_item": {"id": qid, "question": "q", "answer_key": ANSWER_KEY,
                              "evidence_chunk_id": None, "bloom_level": "recall"},
    }


def test_bug1_mastery_persisted_to_learner_state():
    """A correct keypoint answer writes concept mastery back to learner_state (bars move)."""
    c, qid = _seed()
    out = grade_kp_node(_grade_state(qid, ANSWER_KEY), c)  # offline fallback: contains key -> correct
    kp_mastery = out["concept_progress"]["keypoint_state"]["kp1"]["mastery"]
    row = c.execute("SELECT mastery FROM learner_state WHERE concept_id=1").fetchone()
    assert row is not None
    assert row[0] != 0.4, "learner_state was never updated (BUG 1)"
    assert row[0] == kp_mastery, "learner_state must mirror the keypoint mastery"
    # …and the GRAPH-STATE learner_state too (the live agent page + SSE bars read this, not the DB).
    assert out["learner_state"][1]["mastery"] == kp_mastery, "graph-state learner_state must mirror it"


def test_bug5_misconception_detected_from_answer():
    """A wrong answer that voices a misconception is named (not silently None)."""
    c, qid = _seed()
    grade_kp_node(_grade_state(qid, "honestly it's just chain of thought"), c)
    row = c.execute("SELECT score, detected_misconception FROM quiz_attempts").fetchone()
    assert row[0] == 0.0
    assert row[1] == "react_is_just_cot", "keypoint path failed to name the misconception (BUG 5)"


def _advance_state(mastery, correct_obs):
    return {
        "session_id": "s", "route_version": 1,
        "route": [{"concept_id": 1, "step_id": "r1", "status": "pending"}],
        "concept_progress": {"concept_id": 1,
                             "keypoint_state": {"kp1": {"mastery": mastery, "correct_obs": correct_obs}}},
    }


def test_bug2_concede_is_not_reported_as_mastered():
    """Reteach-exhausted at low mastery -> CONCEDE (status conceded), never a false advance."""
    c, _ = _seed()
    out = advance_kp_node(_advance_state(0.30, 0), c)
    assert out["decision"] == "concede"
    assert any(s["status"] == "conceded" for s in out["route"])
    dec = c.execute("SELECT decision FROM decisions ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert dec == "concede"


def test_bug2_true_advance_when_thresholds_met():
    c, _ = _seed()
    out = advance_kp_node(_advance_state(0.90, 3), c)
    assert out["decision"] == "advance"
    assert any(s["status"] == "done" for s in out["route"])


def test_bug3b_posed_question_carries_bloom_level():
    """The tutor exposes the quiz's bloom level so the UI can show it (was '?')."""
    from litnav.ui.interactive import TutorSession
    from litnav.storage.seed import seed_demo_data
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(c)
    seed_demo_data(c, "data/seed/agents_m3.json")
    ts = TutorSession(c, sqlite3.connect(":memory:", check_same_thread=False), "kp-sid")
    ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)
    cur = ts.current()
    assert cur.get("question"), "a keypoint quiz should be posed after TEACH"
    assert cur.get("bloom") in ("recall", "comprehension", "application"), "bloom level not surfaced (BUG 3b)"
