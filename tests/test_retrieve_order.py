import sqlite3
from litnav.nodes.retrieve import retrieve_node
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data


def test_curated_chunks_rank_before_expansion():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m2.json")   # react = concept 1, curated c_react_* chunks
    conn.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, text, chunk_index) "
        "VALUES ('cx_test_0', NULL, 1, 'tangential expansion text', 9)")
    conn.commit()

    out = retrieve_node({"current_concept_id": 1}, conn)
    ids = [e["chunk_id"] for e in out["current_evidence"]]
    assert ids, "react has evidence"
    assert ids[0].startswith("c_") and not ids[0].startswith("cx_"), "curated chunk first"
    assert ids[-1] == "cx_test_0", "expansion chunk pushed to the end"
