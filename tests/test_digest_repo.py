import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo


def _conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    return c


def test_concepts_have_source_and_domain_columns():
    c = _conn()
    cols = {r[1] for r in c.execute("PRAGMA table_info(concepts)").fetchall()}
    assert "source" in cols and "domain" in cols


def test_create_concept_with_source_domain():
    c = _conn()
    repo.create_concept(c, 1, "tool_use", "Tool Use", source="digested", domain="llm-agents")
    row = c.execute("SELECT source, domain FROM concepts WHERE id=1").fetchone()
    assert row == ("digested", "llm-agents")


def test_create_concept_defaults_to_curated():
    c = _conn()
    repo.create_concept(c, 2, "x", "X")
    assert c.execute("SELECT source FROM concepts WHERE id=2").fetchone()[0] == "curated"


def test_record_edge_writes_similarity_and_digested():
    c = _conn()
    repo.create_concept(c, 1, "a", "A")
    repo.create_concept(c, 2, "b", "B")
    repo.record_edge(c, 1, 2, edge_type="similarity", source="digested",
                     confidence=0.9, evidence_chunks=["ch1", "ch2"])
    edges = repo.get_concept_edges(c, source="digested")
    assert len(edges) == 1
    e = edges[0]
    assert e["edge_type"] == "similarity" and e["confidence"] == 0.9
    assert e["evidence"] == ["ch1", "ch2"]


def test_create_keypoint_persists_and_reads_back():
    c = _conn()
    repo.create_concept(c, 1, "a", "A")
    repo.create_keypoint(c, "kp_a_1", 1, "What tools are", "define tool use",
                         evidence_chunk_id=None, sort_order=0, bloom_level="recall")
    kps = repo.get_keypoints(c, 1)
    assert kps and kps[0]["id"] == "kp_a_1" and kps[0]["bloom_level"] == "recall"
