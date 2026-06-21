import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes.review_probe import pose_probe, grade_probe


def _seed():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "t")
    repo.create_concept(c, 1, "react", "ReAct")
    repo.create_keypoint(c, "kp1", 1, "Reason-act", "Explain reason-act.", bloom_level="recall")
    repo.create_quiz_item(c, 1, "What does ReAct interleave?", "reasoning and acting",
                          keypoint_id="kp1", bloom_level="recall")
    repo.upsert_learner_state(c, "s", 1, mastery=0.8, confidence=0.6, n_observations=2)
    return c


def _state(c, **kw):
    base = {"session_id": "s", "route_version": 1,
            "route": [{"step_id": 1, "concept_id": 1, "status": "done"}],
            "learner_state": {1: {"mastery": 0.8}},
            "concept_last_seen": {1: 0}, "step": 3, "pending_answers": [], "history": [],
            "needs_review": [], "now": "2026-06-22T00:00:00"}
    base.update(kw)
    return base


def test_pose_probe_picks_due_concept_and_sets_quiz():
    c = _seed()
    out = pose_probe(_state(c), c, k=2)
    assert out["current_quiz_item"]["concept_id"] == 1
    assert out["current_quiz_item"]["is_retrieval"] is True
    assert out["concept_last_seen"][1] == 3            # refreshed to current step


def test_pose_probe_passthrough_when_nothing_due():
    c = _seed()
    out = pose_probe(_state(c, concept_last_seen={1: 3}, step=3), c, k=2)  # seen this turn
    assert out == {}


def test_grade_probe_correct_reinforces_and_logs_no_reteach():
    c = _seed()
    st = _state(c)
    st.update(pose_probe(st, c, k=2))
    st["pending_answers"] = ["reasoning and acting"]
    out = grade_probe(st, c)
    assert out["learner_state"][1]["mastery"] > 0.8            # reinforced
    assert "reteach" not in (out.get("rationale", "").lower())
    row = c.execute("SELECT predicted, actual FROM retention_log WHERE concept_id=1").fetchone()
    assert row is not None and row[1] == 1.0                   # actual=correct logged


def test_grade_probe_wrong_nudges_and_flags():
    c = _seed()
    st = _state(c)
    st.update(pose_probe(st, c, k=2))
    st["pending_answers"] = ["no idea"]
    out = grade_probe(st, c)
    assert out["learner_state"][1]["mastery"] < 0.8           # nudged down
    assert 1 in out["needs_review"]
    assert c.execute("SELECT actual FROM retention_log WHERE concept_id=1").fetchone()[0] == 0.0
