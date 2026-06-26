import sqlite3
from litnav.storage.schema import init_db
from litnav.discover import query as q
from litnav.llm import router

import os as _os_live
import pytest as _pytest_live
_LIVE_ONLY = _pytest_live.mark.skipif(
    _os_live.getenv("LITNAV_LLM_PROVIDER", "none").lower() == "none",
    reason="live LLM path — activates only when a provider is configured; "
           "skipped in the $0 offline suite",
)


def test_offline_passthrough(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    assert q.to_search_query("给我一个关于 CRISPR 的概览", conn=c, session_id="s") == "给我一个关于 CRISPR 的概览"

@_LIVE_ONLY
def test_uses_llm_query(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"query": "CRISPR gene editing overview"})
    c = sqlite3.connect(":memory:"); init_db(c)
    out = q.to_search_query("给我一个关于 CRISPR 基因编辑的快速概览", conn=c, session_id="s")
    assert out == "CRISPR gene editing overview"

def test_blank_llm_falls_back_to_goal(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"query": ""})
    c = sqlite3.connect(":memory:"); init_db(c)
    assert q.to_search_query("quantum error correction basics", conn=c, session_id="s") == "quantum error correction basics"
