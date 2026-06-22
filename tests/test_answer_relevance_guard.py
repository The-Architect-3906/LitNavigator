"""A6 answer-relevance guard: a clearly off-topic answer must NOT be graded correct, even if the
(live) LLM grader is loose enough to say it captured the key idea. Offline + deterministic ($0):
we inject a stub grader that returns correct=True for an off-topic answer and assert the guard
overrides it to wrong.
"""
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes import grade_kp
from litnav.llm import router

ANSWER_KEY = "thought, action, observation"
QUESTION = "What are the three repeating steps in the ReAct agent loop?"


def _seed():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "topic")
    repo.create_concept(c, 1, "react", "ReAct")
    repo.upsert_learner_state(c, "s", 1, mastery=0.4, confidence=0.0, n_observations=0)
    qid = repo.create_quiz_item(c, 1, QUESTION, ANSWER_KEY,
                                keypoint_id="kp1", bloom_level="recall")
    return c, qid


def _state(qid, answer):
    return {
        "session_id": "s", "route_version": 1, "current_cited_chunks": [],
        "pending_answers": [answer], "user_answer": None,
        "concept_progress": {
            "concept_id": 1, "current_keypoint_id": "kp1", "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.4, "correct_obs": 0}}, "misconceptions": {},
        },
        "current_quiz_item": {"id": qid, "question": QUESTION, "answer_key": ANSWER_KEY,
                              "evidence_chunk_id": None, "bloom_level": "recall"},
    }


def test_off_topic_answer_cannot_pass_even_if_grader_says_correct(monkeypatch):
    # Simulate a LOOSE live grader that wrongly accepts an off-topic carbonara answer.
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"correct": True, "feedback": "Great!", "confidence": 1.0,
                                         "score_0_5": 5, "misconception_resolved": []})
    c, qid = _seed()
    off_topic = "You boil spaghetti, fry the guanciale, and toss it with egg yolk and pecorino."
    out = grade_kp.grade_kp_node(_state(qid, off_topic), c)
    assert out["quiz_result"]["score"] == 0.0, "off-topic answer must not be graded correct (A6)"


def test_on_topic_answer_still_passes(monkeypatch):
    # An on-topic, correct answer is unaffected by the guard.
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"correct": True, "feedback": "Right.", "confidence": 1.0,
                                         "score_0_5": 5, "misconception_resolved": []})
    c, qid = _seed()
    out = grade_kp.grade_kp_node(_state(qid, "thought, then action, then observation"), c)
    assert out["quiz_result"]["score"] == 1.0, "on-topic correct answer must still pass"
