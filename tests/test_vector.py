import sqlite3

from litnav.nodes.retrieve import retrieve_node
from litnav.retrieval import vector
from litnav.retrieval.vector import _cosine, build_index, semantic_search
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_m2.json"
REACT = 1


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    repo.create_session(conn, "s", "agents")
    return conn


def test_cosine_basic():
    assert _cosine([1, 0], [1, 0]) == 1.0
    assert _cosine([1, 0], [0, 1]) == 0.0
    assert abs(_cosine([1, 1], [1, 0]) - 0.7071) < 1e-3


def test_build_index_noop_offline(monkeypatch):
    """provider=none -> embed_texts returns None -> no vectors stored."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    assert build_index(conn) == 0
    assert repo.count_chunk_vectors(conn) == 0


def test_semantic_search_empty_when_no_index(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    assert semantic_search(conn, "react agents") == []


def test_build_and_search_with_fake_embeddings(monkeypatch):
    """Deterministic fake embeddings exercise indexing + ranking without a network call."""
    conn = _conn()
    chunks = conn.execute("SELECT id FROM paper_chunks ORDER BY id").fetchall()
    # Map each chunk id to a distinct orthogonal-ish unit vector; query matches the first.
    ids = [r[0] for r in chunks]

    def fake_embed(texts):
        out = []
        for t in texts:
            # crude bag: vector indexed by which known chunk-id substring appears
            v = [0.0] * (len(ids) + 1)
            matched = False
            for i, cid in enumerate(ids):
                if cid in t:
                    v[i] = 1.0
                    matched = True
            if not matched:
                v[0] = 1.0  # query -> aligns with first chunk's slot
            out.append(v)
        return out

    monkeypatch.setattr(vector.llm_client, "embed_texts", fake_embed)
    n = build_index(conn)
    assert n == len(ids)
    assert repo.count_chunk_vectors(conn) == len(ids)

    hits = semantic_search(conn, ids[0], top_k=2)  # query contains first chunk id
    assert hits and hits[0]["chunk_id"] == ids[0]
    assert hits[0]["score"] >= hits[-1]["score"]


def test_retrieve_node_falls_back_to_concept_tagged(monkeypatch):
    """LITNAV_RETRIEVAL=vector with an empty index -> concept-tagged evidence, not empty."""
    monkeypatch.setenv("LITNAV_RETRIEVAL", "vector")
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    out = retrieve_node({"current_concept_id": REACT, "topic": "agents"}, conn)
    assert out["current_evidence"]
    assert out["current_evidence"][0]["chunk_id"].startswith("c_react")
