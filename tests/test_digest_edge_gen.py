import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import edges
from litnav.llm import router

CONCEPTS = [{"slug": "tool_use", "name": "Tool Use", "domain": "d", "frontier_flag": None},
            {"slug": "react", "name": "ReAct", "domain": "d", "frontier_flag": None}]
CAND = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "react",
        "evidence_chunks": ["c0"], "max_strength": "weak_hint", "multi_paper": False}],
        "similarity_edges": []}

def _di():
    return DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["c0 text", "c1 text"])], [])

def test_live_llm_proposes_edges_over_extracted_slugs(monkeypatch):
    proposed = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "react",
                "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False}],
                "similarity_edges": []}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: proposed)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    pe = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert (pe["prereq_slug"], pe["target_slug"]) == ("tool_use", "react")
    assert pe["confidence"] == 0.75   # 1 chunk, explicit (from the PROPOSAL, not candidate's weak_hint)

def test_proposed_edge_with_unknown_endpoint_is_dropped(monkeypatch):
    proposed = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "GHOST",
                "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False}],
                "similarity_edges": []}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: proposed)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    assert out == []

def test_proposed_edge_with_unreal_evidence_is_dropped(monkeypatch):
    proposed = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "react",
                "evidence_chunks": ["c999"], "max_strength": "explicit_assertion", "multi_paper": False}],
                "similarity_edges": []}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: proposed)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    assert out == []   # c999 is not a real chunk id -> no usable evidence -> dropped

def test_offline_falls_back_to_candidate(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    pe = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert pe["confidence"] == 0.55   # candidate's weak_hint, 1 chunk
