"""Provider-agnostic LLM config: not limited to OpenAI/Qwen.

The registry resolves per-tier models from env (defaults stay OpenAI), and the client picks a base_url
from a preset or LITNAV_LLM_BASE_URL — so any OpenAI-compatible provider works. The model guard still
refuses a per-call model that is neither a configured tier nor the default.
"""
import pytest

from litnav.llm import registry
from litnav.llm import client as c


def test_defaults_unchanged(monkeypatch):
    for v in ("LITNAV_LLM_MODEL", "LITNAV_LLM_MODEL_FRONTIER", "LITNAV_EMBED_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    assert registry.resolve_tier("cheap")["model"] == "gpt-4o-mini"
    assert registry.resolve_tier("frontier")["model"] == "gpt-4o"
    assert registry.resolve_tier("embed")["model"] == "text-embedding-3-small"


def test_env_overrides_tier_models_and_rate(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LITNAV_LLM_MODEL_FRONTIER", "deepseek-reasoner")
    monkeypatch.setenv("LITNAV_EMBED_MODEL", "bge-m3")
    monkeypatch.setenv("LITNAV_LLM_USD_PER_1K", "0.001")
    assert registry.resolve_tier("cheap")["model"] == "deepseek-chat"
    assert registry.resolve_tier("frontier")["model"] == "deepseek-reasoner"
    assert registry.resolve_tier("embed")["model"] == "bge-m3"
    assert registry.resolve_tier("cheap")["usd_per_1k"] == 0.001
    assert {"deepseek-chat", "deepseek-reasoner", "bge-m3"} <= registry.enabled_model_names()


def test_base_url_preset_and_override(monkeypatch):
    monkeypatch.delenv("LITNAV_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "deepseek")
    assert c._base_url() == "https://api.deepseek.com/v1"
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    assert c._base_url() is None                      # default OpenAI endpoint
    monkeypatch.setenv("LITNAV_LLM_BASE_URL", "http://localhost:8000/v1")
    assert c._base_url() == "http://localhost:8000/v1"   # explicit override wins


def test_qwen_default_model_back_compat(monkeypatch):
    monkeypatch.delenv("LITNAV_LLM_MODEL", raising=False)
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "qwen")
    assert registry.resolve_tier("cheap")["model"] == "qwen-plus"
    assert c._base_url() == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_operator_configured_model_is_allowed(monkeypatch):
    # An operator-set model on a non-OpenAI provider must NOT be blocked by the registry guard.
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LITNAV_LLM_MODEL", "deepseek-chat")

    class _Resp:
        def __init__(self): self.choices = [type("M", (), {"message": type("X", (), {"content": "hi"})()})()]
        usage = type("U", (), {"total_tokens": 5})()

    class _Chat:
        def create(self, **kw): assert kw["model"] == "deepseek-chat"; return _Resp()

    class _FakeClient:
        chat = type("C", (), {"completions": _Chat()})()

    monkeypatch.setattr(c, "_client", lambda: _FakeClient())
    assert c.complete_text("p", fallback="fb") == "hi"   # allowed, not refused
