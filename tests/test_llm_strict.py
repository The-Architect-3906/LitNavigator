import pytest
from litnav.llm import client as c


class _Resp:
    def __init__(self, content, tokens):
        self.choices = [type("Ch", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = type("U", (), {"total_tokens": tokens})()


class _FakeChat:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc
    def create(self, **kw):
        if self._exc:
            raise self._exc
        return self._resp


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self.chat = type("C", (), {"completions": _FakeChat(resp, exc)})()


def _set(monkeypatch, *, provider="openai", strict=False, resp=None, exc=None):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", provider)
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1" if strict else "")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=resp, exc=exc))


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
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(exc=RuntimeError("boom")))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    with pytest.raises(c.LivenessError):
        router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb")
    assert cost_repo.session_spend(conn, "s")["tokens"] == 0  # no cost row for a raised call


def test_router_routes_tier_model_to_client_and_ledger(monkeypatch):
    import sqlite3
    from litnav.llm import router
    from litnav.storage.schema import init_db
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_MODEL", "should-be-ignored-by-tier-routing")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=_Resp("hi", 10)))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    router.complete_text("p", tier="frontier", stage="x", session_id="s", conn=conn, fallback="fb")
    router.complete_text("p", tier="cheap", stage="x", session_id="s2", conn=conn, fallback="fb")
    mf = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s'").fetchone()[0]
    mc = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s2'").fetchone()[0]
    assert mf == "gpt-4o"        # frontier tier actually routes gpt-4o
    assert mc == "gpt-4o-mini"   # cheap tier routes gpt-4o-mini; env override is ignored for routed calls
    assert c.last_model() == "gpt-4o-mini"


def test_temperature_zero_passed_to_chat_api(monkeypatch):
    captured = {}
    class _CapChat:
        def create(self, **kw):
            captured.update(kw)
            return _Resp('{"ok": true}', 5)
    class _CapClient:
        def __init__(self):
            self.chat = type("C", (), {"completions": _CapChat()})()
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(c, "_client", lambda: _CapClient())
    c.complete_json("p", fallback={})
    assert captured.get("temperature") == 0.0
    captured.clear()
    c.complete_text("p", fallback="x")
    assert captured.get("temperature") == 0.0


def test_temperature_override_respected(monkeypatch):
    captured = {}
    class _CapChat:
        def create(self, **kw):
            captured.update(kw)
            return _Resp("hi", 5)
    class _CapClient:
        def __init__(self):
            self.chat = type("C", (), {"completions": _CapChat()})()
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(c, "_client", lambda: _CapClient())
    c.complete_text("p", fallback="x", temperature=0.7)
    assert captured.get("temperature") == 0.7


def test_unregistered_model_refused_before_call(monkeypatch):
    # provider=qwen -> actual model "qwen-plus" is NOT in MODEL_REGISTRY -> must be REFUSED (ValueError),
    # not silently fall back. The refusal must happen before any network/_client build.
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")        # even non-strict must refuse (it's a model-enablement guard)
    import pytest as _pytest
    with _pytest.raises(ValueError):
        c.complete_text("p", fallback="fb")
    with _pytest.raises(ValueError):
        c.complete_json("p", fallback={})


def test_registered_model_allowed(monkeypatch):
    # provider=openai default model gpt-4o-mini IS registered -> no refusal
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=_Resp("hi", 5)))
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
