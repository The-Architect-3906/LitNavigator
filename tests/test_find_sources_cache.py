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


def test_second_identical_find_is_cache_hit_and_skips_adapters(monkeypatch):
    calls = {"n": 0}
    def oa(q, k=10, fetch=None):
        calls["n"] += 1
        return [Source("arxiv", "x", "u", "T", 0.9, abstract="a", arxiv_id="x")]
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    oa_desc = _get_descriptor("openalex")
    wp_desc = _get_descriptor("wikipedia")
    monkeypatch.setattr(oa_desc, "search", oa)
    monkeypatch.setattr(wp_desc, "search", lambda *a, **k: [])
    monkeypatch.setattr(fulltext, "attach_fulltext", lambda s, *, top_k: None)
    c = sqlite3.connect(":memory:"); init_db(c)
    r1 = find_sources.find(DiscoverInput("goal", k=2,
                                          selected_adapters=["openalex", "wikipedia"]),
                             conn=c, session_id="s")
    r2 = find_sources.find(DiscoverInput("goal", k=2,
                                          selected_adapters=["openalex", "wikipedia"]),
                             conn=c, session_id="s")
    assert calls["n"] == 1                        # adapters queried only ONCE
    assert r1.cache_hit is False and r2.cache_hit is True
    assert {s.title for s in r2.sources} == {s.title for s in r1.sources}   # same sources re-served


def test_different_goal_is_a_miss(monkeypatch):
    calls = {"n": 0}
    def oa(q, k=10, fetch=None):
        calls["n"] += 1
        return [Source("arxiv", "x", "u", "T", 0.9, abstract="a", arxiv_id="x")]
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    oa_desc = _get_descriptor("openalex")
    wp_desc = _get_descriptor("wikipedia")
    monkeypatch.setattr(oa_desc, "search", oa)
    monkeypatch.setattr(wp_desc, "search", lambda *a, **k: [])
    monkeypatch.setattr(fulltext, "attach_fulltext", lambda s, *, top_k: None)
    c = sqlite3.connect(":memory:"); init_db(c)
    find_sources.find(DiscoverInput("goal A", k=2,
                                    selected_adapters=["openalex", "wikipedia"]),
                       conn=c, session_id="s")
    find_sources.find(DiscoverInput("goal B", k=2,
                                    selected_adapters=["openalex", "wikipedia"]),
                       conn=c, session_id="s")
    assert calls["n"] == 2
