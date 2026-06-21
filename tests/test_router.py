import sqlite3
import pytest
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router
from litnav.llm import client as llm_client


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_offline_returns_fallback_and_records_zero(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    out = router.complete_text("teach this", tier="cheap", stage="teach",
                               session_id="s1", conn=conn, fallback="FALLBACK")
    assert out == "FALLBACK"                       # offline determinism preserved
    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 0 and spend["usd"] == 0.0   # a 0-cost row was recorded


def test_meters_tokens_and_usd(monkeypatch):
    conn = _conn()
    # Fake a live provider: client returns text and reports 1000 tokens.
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "LIVE ANSWER")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 1000)
    out = router.complete_text("x", tier="cheap", stage="teach",
                               session_id="s1", conn=conn, fallback="fb")
    assert out == "LIVE ANSWER"
    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 1000
    assert round(spend["usd"], 4) == 0.0004        # 1000/1000 * cheap rate (0.0004)


def test_disabled_tier_raises_before_any_call(monkeypatch):
    conn = _conn()
    called = {"n": 0}
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: called.__setitem__("n", 1))
    with pytest.raises(ValueError):
        router.complete_text("x", tier="reranker", stage="teach",
                             session_id="s1", conn=conn, fallback="fb")
    assert called["n"] == 0                         # never reached the provider


def test_complete_json_meters(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 200)
    out = router.complete_json("x", tier="frontier", stage="digest",
                               session_id="s1", conn=conn, fallback={"ok": False})
    assert out == {"ok": True}
    assert cost_repo.session_spend(conn, "s1")["tokens"] == 200
