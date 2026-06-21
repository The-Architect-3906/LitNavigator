"""Regression: digested quizzes stored at a bloom OUTSIDE the assess ladder
(recall/comprehension/application) must still be reachable, or the concept always concedes
in the real graph (found by the inner-loop live validation)."""
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo


def test_get_any_quiz_for_kp_rescues_off_ladder_bloom():
    c = sqlite3.connect(":memory:"); init_db(c)
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'x', 'X')")
    # 'understand' is in the 6-level extract vocab but NOT the 3-level assess ladder
    qid = repo.create_quiz_item(c, 1, "What is X?", "the answer", qtype="explain",
                                keypoint_id="kp1", bloom_level="understand")
    assert repo.get_quiz_by_kp_bloom(c, "kp1", "recall") is None        # exact-ladder lookup misses
    got = repo.get_any_quiz_for_kp(c, "kp1")
    assert got and got["answer_key"] == "the answer"                     # rescued regardless of bloom
    assert repo.get_any_quiz_for_kp(c, "kp1", exclude_ids=[qid]) is None  # exclusion honored


def test_get_any_quiz_for_kp_prefers_lower_bloom():
    c = sqlite3.connect(":memory:"); init_db(c)
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'x', 'X')")
    repo.create_quiz_item(c, 1, "Apply?", "a", qtype="explain", keypoint_id="kp1", bloom_level="application")
    repo.create_quiz_item(c, 1, "Recall?", "r", qtype="explain", keypoint_id="kp1", bloom_level="recall")
    got = repo.get_any_quiz_for_kp(c, "kp1")
    assert got["bloom_level"] == "recall"   # prefer the lowest rung
