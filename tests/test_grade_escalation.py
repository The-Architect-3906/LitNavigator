import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes import grade_kp
from litnav.llm import router


def _state(mastery):
    return {"session_id": "s",
            "concept_progress": {"concept_id": 1, "current_keypoint_id": "kp1", "current_bloom": "recall",
                                 "keypoint_state": {"kp1": {"mastery": mastery}}, "misconceptions": {}},
            "current_quiz_item": {"id": 1, "question": "q?", "answer_key": "x", "rubric": "r",
                                  "expected_keypoints": "x", "evidence_chunk_id": None},
            "pending_answers": ["ans"], "user_answer": "ans", "current_cited_chunks": [], "history": []}


def _fake(monkeypatch, cheap_conf):
    calls = {"cheap": 0, "frontier": 0}
    def fake(prompt, *, tier, stage, fallback, **k):
        calls[tier] = calls.get(tier, 0) + 1
        if tier == "frontier":
            return {"correct": True, "feedback": "f", "confidence": 0.95, "score_0_5": 5, "misconception_resolved": []}
        return {"correct": False, "feedback": "f", "confidence": cheap_conf, "score_0_5": 2, "misconception_resolved": []}
    monkeypatch.setattr(router, "complete_json", fake)
    return calls


def test_low_conf_near_threshold_escalates(monkeypatch):
    calls = _fake(monkeypatch, cheap_conf=0.4)        # low confidence
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    grade_kp.grade_kp_node(_state(0.6), c)             # mastery 0.6 is in the near-threshold band
    assert calls["frontier"] == 1                     # escalated to frontier


def test_low_conf_far_from_threshold_no_escalate(monkeypatch):
    calls = _fake(monkeypatch, cheap_conf=0.4)
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    grade_kp.grade_kp_node(_state(0.2), c)            # far below band -> not worth a frontier call
    assert calls["frontier"] == 0


def test_high_conf_no_escalate(monkeypatch):
    calls = _fake(monkeypatch, cheap_conf=0.95)       # confident cheap grade
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    grade_kp.grade_kp_node(_state(0.6), c)
    assert calls["frontier"] == 0
