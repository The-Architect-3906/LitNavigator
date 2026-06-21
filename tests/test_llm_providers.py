"""Provider-agnostic LLM config (via LiteLLM): not limited to OpenAI/Qwen.

The registry resolves per-tier models from env (defaults stay OpenAI); the client maps a bare model
to a LiteLLM 'provider/model' id and passes api_key/api_base — so any LiteLLM-supported provider
(OpenAI, Anthropic, Gemini, DeepSeek, Groq, Ollama, …) works. The guard still refuses a per-call
model that is neither a configured tier nor the default.
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
    monkeypatch.setenv("LITNAV_LLM_MODEL", "claude-3-5-sonnet-latest")
    monkeypatch.setenv("LITNAV_LLM_MODEL_FRONTIER", "claude-3-opus-latest")
    monkeypatch.setenv("LITNAV_EMBED_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("LITNAV_LLM_USD_PER_1K", "0.003")
    assert registry.resolve_tier("cheap")["model"] == "claude-3-5-sonnet-latest"
    assert registry.resolve_tier("frontier")["model"] == "claude-3-opus-latest"
    assert registry.resolve_tier("cheap")["usd_per_1k"] == 0.003
    assert "text-embedding-3-large" in registry.enabled_model_names()


def test_litellm_model_prefixing(monkeypatch):
    # Bare model is prefixed with the provider; a full 'provider/model' id passes through;
    # OpenAI needs no prefix.
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "anthropic")
    assert c._litellm_model("claude-3-5-sonnet-latest") == "anthropic/claude-3-5-sonnet-latest"
    assert c._litellm_model("gemini/gemini-1.5-pro") == "gemini/gemini-1.5-pro"
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    assert c._litellm_model("gpt-4o-mini") == "gpt-4o-mini"


def test_call_kwargs_api_base_and_key(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_API_KEY", "sk-test")
    monkeypatch.delenv("LITNAV_LLM_BASE_URL", raising=False)
    assert c._call_kwargs() == {"api_key": "sk-test"}
    monkeypatch.setenv("LITNAV_LLM_BASE_URL", "http://localhost:11434/v1")   # e.g. a local server
    assert c._call_kwargs()["api_base"] == "http://localhost:11434/v1"


def test_operator_model_allowed_and_prefixed(monkeypatch):
    # An operator-set model on a non-OpenAI provider must NOT be blocked, and must be routed to
    # LiteLLM as 'provider/model'.
    captured = {}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LITNAV_LLM_MODEL", "deepseek-chat")

    class _Resp:
        choices = [type("M", (), {"message": type("X", (), {"content": "hi"})()})()]
        usage = type("U", (), {"total_tokens": 5})()

    def _fake_completion(**kw):
        captured.update(kw)
        return _Resp()

    monkeypatch.setattr(c, "_completion", _fake_completion)
    assert c.complete_text("p", fallback="fb") == "hi"          # allowed, not refused
    assert captured["model"] == "deepseek/deepseek-chat"        # routed with provider prefix


def test_made_up_model_still_refused(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    with pytest.raises(ValueError):
        c.complete_text("p", fallback="fb", model="totally-made-up")


# ── Mixed setup: chat on one provider, embeddings on another ──────────────────────────────────────
class _EmbResp:
    def __init__(self):
        self.data = [{"embedding": [0.1, 0.2]}]
        self.usage = type("U", (), {"total_tokens": 3})()


def test_embed_inherits_chat_provider_when_unset(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_API_KEY", "sk-chat")
    monkeypatch.delenv("LITNAV_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("LITNAV_EMBED_API_KEY", raising=False)
    assert c._embed_provider() == "openai"
    assert c._embed_api_key() == "sk-chat"


def test_mixed_embed_provider_routing(monkeypatch):
    # Chat on Anthropic (no embeddings API); embeddings routed to OpenAI with a separate key.
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LITNAV_LLM_API_KEY", "sk-ant-chat")
    monkeypatch.setenv("LITNAV_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_EMBED_API_KEY", "sk-openai-embed")
    monkeypatch.setenv("LITNAV_EMBED_MODEL", "text-embedding-3-small")
    captured = {}

    def _fake_embedding(**kw):
        captured.update(kw)
        return _EmbResp()

    monkeypatch.setattr(c, "_embedding", _fake_embedding)
    out = c.embed_texts(["hello"])
    assert out == [[0.1, 0.2]]
    assert captured["model"] == "text-embedding-3-small"   # openai → no provider prefix
    assert captured["api_key"] == "sk-openai-embed"        # the EMBED key, not the chat key


def test_mixed_embed_prefixes_nonopenai_provider(monkeypatch):
    monkeypatch.setenv("LITNAV_EMBED_PROVIDER", "gemini")
    monkeypatch.setenv("LITNAV_EMBED_MODEL", "text-embedding-004")
    assert c._litellm_embed_model("text-embedding-004") == "gemini/text-embedding-004"


def test_embed_offline_when_provider_none(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    monkeypatch.delenv("LITNAV_EMBED_PROVIDER", raising=False)
    assert c.embed_texts(["x"]) is None
