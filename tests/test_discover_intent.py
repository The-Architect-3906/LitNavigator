import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import DiscoverInput, Source, DiscoverResult, INTENTS
from litnav.discover import intent as intent_mod


def test_intents_set():
    assert INTENTS == {"crash-course", "systematic", "applied", "reference", "cutting-edge"}


def test_offline_intent_heuristic(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    assert intent_mod.classify("give me a quick intro to multi-agent systems", conn=c, session_id="s") == "crash-course"
    assert intent_mod.classify("a thorough systematic review of agent memory", conn=c, session_id="s") == "systematic"
    assert intent_mod.classify("latest cutting-edge work on agent planning", conn=c, session_id="s") == "cutting-edge"
    assert intent_mod.classify("how do I build a tool-using agent", conn=c, session_id="s") == "applied"
    assert intent_mod.classify("what is a transformer", conn=c, session_id="s") in INTENTS


def test_explicit_intent_passthrough(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    assert intent_mod.classify("anything", conn=c, session_id="s", explicit="applied") == "applied"


def test_source_and_result_shapes():
    s = Source(source_type="arxiv", source_id="2210.03629", url="http://x", title="ReAct",
               authority_score=0.9, why="seminal", abstract="...", arxiv_id="2210.03629")
    r = DiscoverResult(sources=[s], intent_used="applied")
    assert r.sources[0].arxiv_id == "2210.03629" and r.intent_used == "applied"
