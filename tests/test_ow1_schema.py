import sqlite3
from litnav.storage.schema import init_db


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def test_new_columns_present():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert "bloom_level" in _cols(conn, "keypoints")
    assert {"distractors_json", "irt_b"} <= _cols(conn, "quiz_items")
    assert {"source_type", "url"} <= _cols(conn, "papers")
    assert "irt_theta" in _cols(conn, "learner_state")


def test_new_tables_present():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert {"learner_goal", "review_queue", "digest_cache"} <= _tables(conn)


def test_similarity_and_digested_edges_insertable():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1,'a','A'),(2,'b','B')")
    conn.execute("INSERT INTO concept_edges (prereq_concept, target_concept, edge_type, source) "
                 "VALUES (1,2,'similarity','digested')")
    row = conn.execute("SELECT edge_type, source FROM concept_edges").fetchone()
    assert row == ("similarity", "digested")


def test_existing_suite_unaffected_smoke():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert {"concepts", "concept_edges", "quiz_items", "learner_state", "cost_ledger"} <= _tables(conn)
