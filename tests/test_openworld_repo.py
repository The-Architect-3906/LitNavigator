import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import openworld_repo as ow


def _conn():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    conn.execute("INSERT INTO sessions (id, topic, status) VALUES ('s','t','active')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1,'a','A'),(2,'b','B')")
    return conn


def test_learner_goal_set_get():
    conn = _conn()
    ow.set_goal(conn, "s", "learn A", "functional", [1, 2])
    g = ow.get_goal(conn, "s")
    assert g["goal_text"] == "learn A"
    assert g["goal_type"] == "functional"
    assert g["target_concepts"] == [1, 2]
    ow.set_goal(conn, "s", "learn A deeply", "mastery", [1])
    g2 = ow.get_goal(conn, "s")
    assert g2["goal_type"] == "mastery" and g2["target_concepts"] == [1]


def test_learner_goal_missing_is_none():
    assert ow.get_goal(_conn(), "nobody") is None


def test_review_queue_enqueue_and_due():
    conn = _conn()
    ow.enqueue_review(conn, "s", 1, due_at="2026-06-20T00:00:00", fsrs_state={"stability": 1.0})
    ow.enqueue_review(conn, "s", 2, due_at="2026-06-25T00:00:00", fsrs_state={"stability": 2.0})
    due = ow.due_reviews(conn, "s", now="2026-06-21T00:00:00")
    assert [d["concept_id"] for d in due] == [1]
    assert due[0]["fsrs_state"] == {"stability": 1.0}
    ow.enqueue_review(conn, "s", 1, due_at="2026-07-01T00:00:00", fsrs_state={"stability": 5.0})
    assert ow.due_reviews(conn, "s", now="2026-06-21T00:00:00") == []


def test_digest_cache_miss_then_hit():
    conn = _conn()
    assert ow.cache_get(conn, "linear-algebra::eigen") is None
    ow.cache_put(conn, "linear-algebra::eigen", graph_version=1, human_checked=False)
    hit = ow.cache_get(conn, "linear-algebra::eigen")
    assert hit["status"] == "cached" and hit["graph_version"] == 1
