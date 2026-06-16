import sqlite3

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data


def test_seed_demo_data_writes_core_tables(tmp_path):
    db_path = tmp_path / "litnav.sqlite"
    conn = sqlite3.connect(db_path)
    init_db(conn)
    seed_demo_data(conn, "data/seed/rag_demo.json")

    assert conn.execute("SELECT count(*) FROM concepts").fetchone()[0] == 5
    assert conn.execute("SELECT count(*) FROM concept_edges").fetchone()[0] == 4
    assert conn.execute("SELECT count(*) FROM paper_chunks").fetchone()[0] == 5
    assert conn.execute("SELECT count(*) FROM quiz_items").fetchone()[0] == 5
