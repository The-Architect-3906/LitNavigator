import sqlite3

from litnav.graph.builder import run_m0_session
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data


def _setup(tmp_path):
    conn = sqlite3.connect(tmp_path / "litnav.sqlite")
    init_db(conn)
    seed_demo_data(conn, "data/seed/rag_demo.json")
    return conn


def test_m0_session_writes_all_required_rows(tmp_path):
    conn = _setup(tmp_path)
    session_id = run_m0_session(conn, answer="embedding vectors")

    assert conn.execute(
        "SELECT count(*) FROM sessions WHERE id=?", (session_id,)
    ).fetchone()[0] == 1

    assert conn.execute(
        "SELECT count(*) FROM route_steps WHERE session_id=?", (session_id,)
    ).fetchone()[0] >= 1

    assert conn.execute(
        "SELECT count(*) FROM learner_state WHERE session_id=?", (session_id,)
    ).fetchone()[0] >= 1

    assert conn.execute(
        "SELECT count(*) FROM quiz_attempts WHERE session_id=?", (session_id,)
    ).fetchone()[0] == 1

    assert conn.execute(
        "SELECT count(*) FROM decisions WHERE session_id=?", (session_id,)
    ).fetchone()[0] == 1


def test_m0_correct_answer_advances(tmp_path):
    conn = _setup(tmp_path)
    session_id = run_m0_session(conn, answer="embedding vectors")

    decision = conn.execute(
        "SELECT decision FROM decisions WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    assert decision == "advance"


def test_m0_wrong_answer_does_not_advance(tmp_path):
    conn = _setup(tmp_path)
    session_id = run_m0_session(conn, answer="keyword matching")

    decision = conn.execute(
        "SELECT decision FROM decisions WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    assert decision != "advance"


def test_m0_learner_state_mastery_updated(tmp_path):
    conn = _setup(tmp_path)
    session_id = run_m0_session(conn, answer="embedding vectors")

    mastery = conn.execute(
        "SELECT mastery FROM learner_state WHERE session_id=? AND concept_id=1", (session_id,)
    ).fetchone()[0]
    assert mastery > 0.4
