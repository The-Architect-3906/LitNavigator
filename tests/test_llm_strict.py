import pytest
from litnav.llm import client as c


class _Resp:
    def __init__(self, content, tokens):
        self.choices = [type("Ch", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = type("U", (), {"total_tokens": tokens})()


def _fake_completion(resp=None, exc=None, capture=None):
    """Build a stand-in for c._completion (the LiteLLM seam)."""
    def _f(**kw):
        if capture is not None:
            capture.update(kw)
        if exc:
            raise exc
        return resp
    return _f


def _set(monkeypatch, *, provider="openai", strict=False, resp=None, exc=None):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", provider)
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1" if strict else "")
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=resp, exc=exc))


def test_success_sets_was_live_and_tokens(monkeypatch):
    _set(monkeypatch, resp=_Resp('{"ok": true}', 42))
    out = c.complete_json("p", fallback={"ok": False})
    assert out == {"ok": True} and c.was_live() is True and c.last_token_cost() == 42


def test_provider_none_never_live_never_raises(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1")
    assert c.complete_json("p", fallback={"x": 1}) == {"x": 1}
    assert c.was_live() is False


def test_non_strict_error_falls_back(monkeypatch):
    _set(monkeypatch, strict=False, exc=RuntimeError("429"))
    assert c.complete_text("p", fallback="fb") == "fb"
    assert c.was_live() is False


def test_strict_error_raises_liveness(monkeypatch):
    _set(monkeypatch, strict=True, exc=RuntimeError("429"))
    with pytest.raises(c.LivenessError):
        c.complete_text("p", fallback="fb")


def test_strict_success_does_not_raise(monkeypatch):
    _set(monkeypatch, strict=True, resp=_Resp("hello", 7))
    assert c.complete_text("p", fallback="fb") == "hello"
    assert c.was_live() is True


def test_router_propagates_liveness_error_and_records_no_cost(monkeypatch):
    import sqlite3
    from litnav.llm import router
    from litnav.storage.schema import init_db
    from litnav.storage import cost_repo
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1")
    monkeypatch.setattr(c, "_completion", _fake_completion(exc=RuntimeError("boom")))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    with pytest.raises(c.LivenessError):
        router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb")
    assert cost_repo.session_spend(conn, "s")["tokens"] == 0  # no cost row for a raised call


def test_router_routes_tier_model_to_client_and_ledger(monkeypatch):
    import sqlite3
    from litnav.llm import router
    from litnav.storage.schema import init_db
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    # Env-configured tier models flow through router -> client -> ledger (provider-agnostic).
    monkeypatch.setenv("LITNAV_LLM_MODEL", "my-cheap-model")
    monkeypatch.setenv("LITNAV_LLM_MODEL_FRONTIER", "my-frontier-model")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=_Resp("hi", 10)))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    router.complete_text("p", tier="frontier", stage="x", session_id="s", conn=conn, fallback="fb")
    router.complete_text("p", tier="cheap", stage="x", session_id="s2", conn=conn, fallback="fb")
    mf = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s'").fetchone()[0]
    mc = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s2'").fetchone()[0]
    assert mf == "my-frontier-model"   # frontier tier routes the env-configured frontier model
    assert mc == "my-cheap-model"      # cheap tier routes the env-configured model
    assert c.last_model() == "my-cheap-model"


def test_temperature_zero_passed_to_chat_api(monkeypatch):
    captured = {}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=_Resp('{"ok": true}', 5), capture=captured))
    c.complete_json("p", fallback={})
    assert captured.get("temperature") == 0.0
    captured.clear()
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=_Resp("hi", 5), capture=captured))
    c.complete_text("p", fallback="x")
    assert captured.get("temperature") == 0.0


def test_temperature_override_respected(monkeypatch):
    captured = {}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=_Resp("hi", 5), capture=captured))
    c.complete_text("p", fallback="x", temperature=0.7)
    assert captured.get("temperature") == 0.7


def test_unregistered_model_refused_before_call(monkeypatch):
    # A per-call model that is neither a configured tier model nor the default must be REFUSED
    # (ValueError) — catches typo'd in-code model names. Refusal happens before any _client build.
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")        # even non-strict must refuse (model-config guard)
    import pytest as _pytest
    with _pytest.raises(ValueError):
        c.complete_text("p", fallback="fb", model="totally-made-up-model")
    with _pytest.raises(ValueError):
        c.complete_json("p", fallback={}, model="totally-made-up-model")


def test_registered_model_allowed(monkeypatch):
    # provider=openai default model gpt-4o-mini IS registered -> no refusal
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(c, "_completion", _fake_completion(resp=_Resp("hi", 5)))
    assert c.complete_text("p", fallback="fb") == "hi"


def test_budget_80pct_alert(monkeypatch):
    import sqlite3, warnings
    from litnav.llm import router
    from litnav.storage.schema import init_db
    monkeypatch.setattr(c, "complete_text", lambda *a, **k: "x")   # bypass real client in router test
    monkeypatch.setattr(c, "last_token_cost", lambda: 850)
    monkeypatch.setattr(c, "last_model", lambda: "gpt-4o-mini")
    conn = sqlite3.connect(":memory:"); init_db(conn)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb", budget=1000)
    assert any("80%" in str(x.message) or ">=80" in str(x.message).lower() for x in w)  # alert fired at 850/1000
    assert router.over_budget_fraction(conn, "s", 1000) == 0.85
