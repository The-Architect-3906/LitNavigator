"""LLM + embedding client.

Provider is selected by LITNAV_LLM_PROVIDER:
  - none   (default): no calls; complete_json returns the caller's fallback, embed_texts -> None.
  - any OpenAI-compatible provider: openai (default endpoint), or one with a built-in base_url preset
    (qwen, deepseek, groq, openrouter, together, ollama), or ANY other endpoint via LITNAV_LLM_BASE_URL
    (Azure / vLLM / a local server / a proxy). Not limited to OpenAI and Qwen.

Models come from the registry tiers, which read LITNAV_LLM_MODEL / LITNAV_LLM_MODEL_FRONTIER /
LITNAV_EMBED_MODEL (see llm/registry.py). Key comes from LITNAV_LLM_API_KEY (or OPENAI_API_KEY) —
never hard-coded. Every caller passes a deterministic fallback, so the system always runs offline.
"""
from __future__ import annotations

import os
import threading

from litnav.llm import registry

# Per-thread token cost: each calling thread sees its own counter so concurrent
# sessions do not bleed cost into each other's records.
_tls = threading.local()


class LivenessError(RuntimeError):
    """Raised in strict mode when a live LLM/embed call fails instead of silently falling back."""


def _strict() -> bool:
    return os.getenv("LITNAV_LLM_STRICT", "") not in ("", "0", "false", "False")


def was_live() -> bool:
    """True iff the most recent call on this thread parsed a real response with tokens>0
    (provider=none and the silent-fallback path both leave this False)."""
    return bool(getattr(_tls, "was_live", False))


def last_token_cost() -> int:
    """Token cost of the most recent call on this thread (0 when offline / no usage)."""
    return getattr(_tls, "cost", 0)


def last_model() -> str | None:
    """Actual model string used by the most recent call on this thread (None when offline)."""
    return getattr(_tls, "model", None)


def _provider() -> str:
    return os.getenv("LITNAV_LLM_PROVIDER", "none")


def _api_key() -> str:
    return os.getenv("LITNAV_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")


def _chat_model() -> str:
    # The default chat model = the cheap tier (registry resolves env overrides + provider defaults).
    return registry.resolve_tier("cheap")["model"]


def _embed_model() -> str:
    return registry.resolve_tier("embed")["model"]


# Built-in base_url presets for common OpenAI-compatible providers. ANY other provider works by
# setting LITNAV_LLM_BASE_URL explicitly. "openai" uses the SDK default endpoint (no base_url).
_PROVIDER_BASE_URLS: dict[str, str] = {
    "qwen":       "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together":   "https://api.together.xyz/v1",
    "ollama":     "http://localhost:11434/v1",
}


def _base_url() -> str | None:
    # Explicit override always wins; else a built-in preset for the named provider; else default.
    return os.getenv("LITNAV_LLM_BASE_URL") or _PROVIDER_BASE_URLS.get(_provider())


def _client():
    from openai import OpenAI
    base = _base_url()
    return OpenAI(api_key=_api_key(), base_url=base) if base else OpenAI(api_key=_api_key())


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict, model: str | None = None, temperature: float = 0.0) -> dict:
    """Return a JSON dict from the configured LLM, or `fallback` when provider=none / on error."""
    _tls.cost = 0
    _tls.was_live = False
    _tls.model = None
    if _provider() == "none":
        return fallback
    actual = model or _chat_model()
    if actual not in registry.enabled_model_names():
        raise ValueError(
            f"model {actual!r} is not a configured tier model (set LITNAV_LLM_MODEL / "
            f"LITNAV_LLM_MODEL_FRONTIER; provider={_provider()!r}). "
            f"Configured: {sorted(registry.enabled_model_names())}."
        )
    _tls.model = actual
    try:
        import json
        response = _client().chat.completions.create(
            model=actual,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
            timeout=30,
        )
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        result = json.loads(response.choices[0].message.content)
        _tls.was_live = _tls.cost > 0
        return result
    except Exception as e:
        if _strict():
            raise LivenessError(f"complete_json failed in strict mode: {e}") from e
        return fallback


def complete_text(prompt: str, *, fallback: str, max_tokens: int = 400, model: str | None = None, temperature: float = 0.0) -> str:
    """Return a free-text completion (e.g. a grounded teaching turn), or `fallback` offline/on error."""
    _tls.cost = 0
    _tls.was_live = False
    _tls.model = None
    if _provider() == "none":
        return fallback
    actual = model or _chat_model()
    if actual not in registry.enabled_model_names():
        raise ValueError(
            f"model {actual!r} is not a configured tier model (set LITNAV_LLM_MODEL / "
            f"LITNAV_LLM_MODEL_FRONTIER; provider={_provider()!r}). "
            f"Configured: {sorted(registry.enabled_model_names())}."
        )
    _tls.model = actual
    try:
        response = _client().chat.completions.create(
            model=actual,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=30,
        )
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        _tls.was_live = _tls.cost > 0
        return response.choices[0].message.content or fallback
    except Exception as e:
        if _strict():
            raise LivenessError(f"complete_text failed in strict mode: {e}") from e
        return fallback


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Return one embedding vector per text, or None when offline (provider=none) / on error."""
    _tls.cost = 0
    _tls.was_live = False
    _tls.model = None
    if _provider() == "none" or not texts:
        return None
    try:
        _tls.model = _embed_model()
        response = _client().embeddings.create(model=_embed_model(), input=list(texts))
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        _tls.was_live = _tls.cost > 0
        return [d.embedding for d in response.data]
    except Exception as e:
        if _strict():
            raise LivenessError(f"embed_texts failed in strict mode: {e}") from e
        return None
