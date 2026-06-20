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
