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


def test_ledger_records_actual_model_not_registry_name(monkeypatch):
    import sqlite3
    from litnav.llm import router
    from litnav.storage.schema import init_db
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_MODEL", "gpt-4o-mini-2024-07-18")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=_Resp("hi", 10)))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb")
    m = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s'").fetchone()[0]
    assert m == "gpt-4o-mini-2024-07-18"   # the ACTUAL env model, not registry "gpt-4o-mini"
