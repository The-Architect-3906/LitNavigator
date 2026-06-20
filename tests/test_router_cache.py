import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, client as c

def test_router_cache_hit_is_zero_cost_and_skips_model(monkeypatch):
    calls = {"n": 0}
    def fake(prompt, *, schema_hint="", fallback, model=None, temperature=0.0):
        calls["n"] += 1
        return {"ok": True}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(c, "complete_json", fake)
    monkeypatch.setattr(c, "last_token_cost", lambda: 100)
    monkeypatch.setattr(c, "last_model", lambda: "gpt-4o-mini")
    monkeypatch.setattr(c, "embed_texts", lambda t: [[1.0, 0.0]])   # stable embedding
    conn = sqlite3.connect(":memory:"); init_db(conn)
    r1 = router.complete_json("p", tier="cheap", stage="digest", fallback={}, session_id="s", conn=conn, cache=True)
    r2 = router.complete_json("p", tier="cheap", stage="digest", fallback={}, session_id="s", conn=conn, cache=True)
    assert r1 == r2 == {"ok": True}
    assert calls["n"] == 1                                   # second served from cache
    rows = conn.execute("SELECT total_tokens, cache_hit FROM cost_ledger ORDER BY id").fetchall()
    assert rows[0] == (100, 0) and rows[1] == (0, 1)         # 2nd is a $0 cache-hit row
