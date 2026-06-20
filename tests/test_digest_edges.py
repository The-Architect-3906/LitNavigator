import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import edges


CONCEPTS = [
    {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
    {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
]
CANDIDATE = {
    "prereq_edges": [
        {"prereq_slug": "tool_use", "target_slug": "reason_act",
         "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False},
    ],
    "similarity_edges": [
        {"a_slug": "tool_use", "b_slug": "reason_act",
         "evidence_chunks": ["c0", "c1"], "max_strength": "general_statement", "multi_paper": True},
    ],
}


def _input(targets=None):
    return DigestInput("llm-agents",
                       [SourceDoc("arxiv", "x", "X", None, ["c0 text", "c1 text"])],
                       target_slugs=targets or [])


def test_prereq_edge_confidence_is_rule_computed(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(), CONCEPTS, candidate=CANDIDATE, session_id="s", conn=c)
    prereq = [e for e in out if e["edge_type"] == "prerequisite"]
    assert len(prereq) == 1
    assert prereq[0]["confidence"] == 0.75          # 1 chunk, explicit, single
    assert prereq[0]["high_impact"] is True          # target_slugs=[] -> all impactful


def test_similarity_edge_confidence_is_rule_computed(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(), CONCEPTS, candidate=CANDIDATE, session_id="s", conn=c)
    sim = [e for e in out if e["edge_type"] == "similarity"]
    assert len(sim) == 1
    assert sim[0]["confidence"] == 0.90              # 2 chunks, general, multi
    assert sim[0]["high_impact"] is False            # similarity edges are never high-impact


def test_high_impact_only_for_targeted_slice(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(targets=["tool_use"]), CONCEPTS, candidate=CANDIDATE,
                            session_id="s", conn=c)
    prereq = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert prereq["high_impact"] is False            # reason_act not in targets
