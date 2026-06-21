import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import Source
from litnav.discover import relevance
from litnav.llm import router

def _src(t, a=""):
    return Source(source_type="web", source_id=t, url="u", title=t, abstract=a, authority_score=0.5)

def test_offline_passthrough(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("A"), _src("B")]
    assert relevance.relevance_gate("topic", srcs, conn=c, session_id="s") == srcs

def test_drops_irrelevant_keeps_rank_order(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": [0, 2]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("Raft paper"), _src("Megalopolis film"), _src("Paxos paper")]
    out = relevance.relevance_gate("raft consensus", srcs, conn=c, session_id="s", min_keep=1)
    assert [s.title for s in out] == ["Raft paper", "Paxos paper"]

def test_never_starves(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": []})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("A"), _src("B"), _src("C")]
    out = relevance.relevance_gate("topic", srcs, conn=c, session_id="s", min_keep=2)
    assert [s.title for s in out] == ["A", "B"]   # all dropped -> keep top min_keep by rank order

def test_empty_input(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": []})
    c = sqlite3.connect(":memory:"); init_db(c)
    assert relevance.relevance_gate("topic", [], conn=c, session_id="s") == []
