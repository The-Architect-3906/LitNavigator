import sqlite3
import pytest
from litnav.storage.schema import init_db
from litnav.llm import router, BudgetExceeded   # re-exported for convenience (added in Step 3)
from litnav.llm import client as llm_client


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_budget_trips_after_spend_reaches_cap(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "ok")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 600)
    # budget=1000; first call records 600 (<1000) -> ok; second reaches 1200 (>=1000) -> raise.
    router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                         fallback="fb", budget=1000)
    with pytest.raises(BudgetExceeded):
        router.complete_text("b", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb", budget=1000)


def test_no_budget_never_trips(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "ok")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 10_000)
    for _ in range(5):
        router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb")  # budget=None -> never raises


def test_offline_never_trips_budget(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    for _ in range(100):
        router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb", budget=1)   # offline cost is 0 -> never reaches 1
