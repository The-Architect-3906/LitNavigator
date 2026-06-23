"""Regression for the removed A6 answer-relevance guard (live-test B7).

The old word-overlap guard was English/Latin-only and force-failed CORRECT non-English answers
(a correct French/Spanish answer shares no Latin content words with an English answer_key → it was
flagged off-topic → graded wrong). It was removed. These tests assert grading now defers to the
grader verdict regardless of answer language — no deterministic overlap check overrides 'correct'.
"""
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes import grade_kp
from litnav.llm import router


def _seed():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "topic")
    repo.create_concept(c, 1, "attention", "Attention")
    repo.upsert_learner_state(c, "s", 1, mastery=0.4, confidence=0.0, n_observations=0)
    qid = repo.create_quiz_item(c, 1, "What does attention compute?",
                                "weighted relevance over tokens",
                                keypoint_id="kp1", bloom_level="recall")
    return c, qid


def _state(qid, answer):
    return {
        "session_id": "s", "route_version": 1, "current_cited_chunks": [],
        "pending_answers": [answer], "user_answer": None,
        "concept_progress": {
            "concept_id": 1, "current_keypoint_id": "kp1", "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.3, "correct_obs": 0}}, "misconceptions": {},
        },
        "current_quiz_item": {"id": qid, "question": "What does attention compute?",
                              "answer_key": "weighted relevance over tokens",
                              "evidence_chunk_id": None, "bloom_level": "recall"},
    }


def test_correct_french_answer_not_force_failed(monkeypatch):
    """A grader 'correct' on a French answer must NOT be overridden to wrong by an overlap check."""
    c, qid = _seed()
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"correct": True, "feedback": "Correct.", "confidence": 1.0,
                                         "score_0_5": 5, "misconception_resolved": []})
    grade_kp.grade_kp_node(_state(qid, "elle pondère la pertinence de chaque jeton"), c)
    row = c.execute("SELECT score FROM quiz_attempts WHERE quiz_item_id=?", (qid,)).fetchone()
    assert row[0] == 1.0, "correct French answer was wrongly failed (the removed guard regression)"


def test_grader_wrong_still_wrong(monkeypatch):
    """No guard means we faithfully follow the grader: a 'wrong' verdict stays wrong."""
    c, qid = _seed()
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"correct": False, "feedback": "Not quite.", "confidence": 1.0,
                                         "score_0_5": 1, "misconception_resolved": []})
    grade_kp.grade_kp_node(_state(qid, "something off"), c)
    row = c.execute("SELECT score FROM quiz_attempts WHERE quiz_item_id=?", (qid,)).fetchone()
    assert row[0] == 0.0
