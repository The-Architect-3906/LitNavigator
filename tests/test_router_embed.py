import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, registry
from litnav.llm import client as llm_client


def test_embed_tier_is_enabled():
    assert registry.is_enabled("embed")
    assert registry.resolve_tier("embed")["model"]


def test_offline_embed_returns_none_and_records_zero(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = router.embed_texts(["a", "b"], stage="digest", session_id="s", conn=c)
    assert out is None
    assert cost_repo.session_spend(c, "s")["tokens"] == 0


def test_live_embed_meters_tokens(monkeypatch):
    c = sqlite3.connect(":memory:"); init_db(c)
    monkeypatch.setattr(llm_client, "embed_texts", lambda texts: [[0.1, 0.2]] * len(texts))
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 42)
    out = router.embed_texts(["a", "b"], stage="digest", session_id="s", conn=c)
    assert out == [[0.1, 0.2], [0.1, 0.2]]
    assert cost_repo.session_spend(c, "s")["tokens"] == 42
