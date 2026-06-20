import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline

CAND = {
    "concepts": [{"slug": "a", "name": "A", "domain": "d", "frontier_flag": None},
                 {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None}],
    "keypoints": [], "prereq_edges": [
        {"prereq_slug": "a", "target_slug": "b", "evidence_chunks": ["c0"],
         "max_strength": "explicit_assertion", "multi_paper": False}],
    "similarity_edges": [], "quiz_seeds": [], "judge_labels": {"a->b": True},
}

def _di():
    return DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["t0", "t1"])], [])

def test_cache_hit_rereads_populated_graph(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    r1 = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    assert r1.cache_hit is False and len(r1.edges) >= 1
    r2 = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    assert r2.cache_hit is True
    assert {x["slug"] for x in r2.concepts} == {"a", "b"}
    assert any(e["edge_type"] == "prerequisite" for e in r2.edges)

def test_model_key_change_invalidates_cache(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    r = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s", model_key="other-model")
    assert r.cache_hit is False
