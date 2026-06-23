import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import DiscoverInput, Source
from litnav.discover import find_sources
from litnav.discover.adapters import registry as adapter_registry
from litnav.discover import fulltext


def _get_descriptor(adapter_id: str):
    """Return the AdapterDescriptor for the given id."""
    for ad in adapter_registry.available_adapters():
        if ad.id == adapter_id:
            return ad
    raise KeyError(adapter_id)


def test_orchestrator_merges_ranks_and_attaches_fulltext(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    oa_desc = _get_descriptor("openalex")
    wp_desc = _get_descriptor("wikipedia")
    monkeypatch.setattr(oa_desc, "search",
        lambda q, k=10, fetch=None: [Source("arxiv", "2210.03629", "u", "ReAct", 0.9, abstract="reasoning acting", arxiv_id="2210.03629")])
    monkeypatch.setattr(wp_desc, "search",
        lambda q, k=5, fetch=None: [Source("wikipedia", "Agent", "w", "Software agent", 0.5, abstract="an agent")])
    monkeypatch.setattr(fulltext, "attach_fulltext",
        lambda sources, *, top_k: [setattr(s, "chunks", ["full text"]) for s in sources[:top_k]])
    c = sqlite3.connect(":memory:"); init_db(c)
    res = find_sources.find(DiscoverInput("how to build a react agent", k=2,
                                          selected_adapters=["openalex", "wikipedia"]),
                             conn=c, session_id="s")
    from litnav.discover.contract import INTENTS
    assert res.intent_used in INTENTS
    assert 1 <= len(res.sources) <= 2
    assert "ReAct" in {s.title for s in res.sources}
    assert any(s.chunks for s in res.sources)
    assert all(s.why for s in res.sources)   # each source has a 'why'


def test_adapter_failure_is_non_fatal(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    def boom(q, k=10, fetch=None):
        raise RuntimeError("openalex down")
    oa_desc = _get_descriptor("openalex")
    wp_desc = _get_descriptor("wikipedia")
    monkeypatch.setattr(oa_desc, "search", boom)
    monkeypatch.setattr(wp_desc, "search",
        lambda q, k=5, fetch=None: [Source("wikipedia", "A", "w", "Agent", 0.5, abstract="x")])
    monkeypatch.setattr(fulltext, "attach_fulltext", lambda sources, *, top_k: None)
    c = sqlite3.connect(":memory:"); init_db(c)
    res = find_sources.find(DiscoverInput("agents", k=3,
                                          selected_adapters=["openalex", "wikipedia"]),
                             conn=c, session_id="s")
    assert {s.title for s in res.sources} == {"Agent"}   # survived the OpenAlex failure
