"""LLM + embedding client — provider-agnostic via LiteLLM.

LitNavigator works with ANY provider LiteLLM supports — OpenAI, Anthropic, Google Gemini, DeepSeek,
Groq, Mistral, Cohere, Together, OpenRouter, AWS Bedrock, Azure, Ollama / vLLM / any self-hosted
OpenAI-compatible server, etc. — not just OpenAI/Qwen. One code path; LiteLLM handles each provider's
auth, request/response shape, and JSON mode.

Selection (see also llm/registry.py, which resolves the per-tier model strings):
  - LITNAV_LLM_PROVIDER : "none" (default) = fully offline, no calls; otherwise the live provider
                          (also used as the model prefix when the model name has no "provider/" part).
  - LITNAV_LLM_MODEL / LITNAV_LLM_MODEL_FRONTIER / LITNAV_EMBED_MODEL : model ids. Either a bare name
    (combined with the provider, e.g. provider=anthropic + model=claude-3-5-sonnet-latest →
    "anthropic/claude-3-5-sonnet-latest") or a full LiteLLM id with a "provider/" prefix.
  - LITNAV_LLM_API_KEY (or OPENAI_API_KEY) : the key, passed to LiteLLM. Never hard-coded.
  - LITNAV_LLM_BASE_URL : optional endpoint override (Azure / vLLM / a proxy / a self-hosted or any
    OpenAI-compatible server such as DashScope for Qwen).

Mixed setup: embeddings (used for source re-ranking) can use a SEPARATE provider via
LITNAV_EMBED_PROVIDER / LITNAV_EMBED_API_KEY / LITNAV_EMBED_BASE_URL (each falls back to its
LITNAV_LLM_* counterpart). So a chat-only provider (e.g. Anthropic, which has no embeddings API) can
pair with an embedding-capable one (e.g. OpenAI) instead of degrading to keyword-only ranking.

Every caller passes a deterministic fallback, so the system always runs offline ($0, no key).
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


def _litellm_model(name: str) -> str:
    """Map a tier model name to a LiteLLM model id. A name that already carries a 'provider/' prefix
    is used as-is; a bare name is prefixed with the configured provider (OpenAI needs no prefix)."""
    if "/" in name:
        return name
    prov = _provider()
    if prov in ("", "none", "openai"):
        return name
    return f"{prov}/{name}"


def _call_kwargs() -> dict:
    kw: dict = {}
    key = _api_key()
    if key:
        kw["api_key"] = key
    base = os.getenv("LITNAV_LLM_BASE_URL")
    if base:
        kw["api_base"] = base
    return kw


# ── Embeddings can use a SEPARATE provider/key/endpoint ("mixed setup") ───────────────────────────
# So a chat-only provider (Anthropic, Groq, …) can still do source re-ranking by routing embeddings
# to an embedding-capable provider. Each LITNAV_EMBED_* falls back to its LITNAV_LLM_* counterpart, so
# a single-provider setup needs no extra config.
def _embed_provider() -> str:
    return os.getenv("LITNAV_EMBED_PROVIDER") or _provider()


def _embed_api_key() -> str:
    return os.getenv("LITNAV_EMBED_API_KEY") or _api_key()


def _litellm_embed_model(name: str) -> str:
    if "/" in name:
        return name
    prov = _embed_provider()
    if prov in ("", "none", "openai"):
        return name
    return f"{prov}/{name}"


def _embed_call_kwargs() -> dict:
    kw: dict = {}
    key = _embed_api_key()
    if key:
        kw["api_key"] = key
    base = os.getenv("LITNAV_EMBED_BASE_URL")
    if not base and _embed_provider() == _provider():
        base = os.getenv("LITNAV_LLM_BASE_URL")  # inherit only when same provider
    if base:
        kw["api_base"] = base
    return kw


_lib_cache = None


def _lib():
    """Import LiteLLM lazily and set safe global flags once (kept out of import time)."""
    global _lib_cache
    if _lib_cache is None:
        import litellm
        litellm.drop_params = True       # ignore params a provider doesn't support (don't error)
        litellm.telemetry = False
        try:
            litellm.suppress_debug_info = True
        except Exception:
            pass
        _lib_cache = litellm
    return _lib_cache


def _completion(**kwargs):
    """Seam over litellm.completion (monkeypatched in tests)."""
    return _lib().completion(**kwargs)


def _embedding(**kwargs):
    """Seam over litellm.embedding (monkeypatched in tests)."""
    return _lib().embedding(**kwargs)


def _usage_tokens(resp) -> int:
    try:
        u = getattr(resp, "usage", None)
        return int((u.total_tokens if u and u.total_tokens else 0) or 0)
    except Exception:
        return 0


def _guard(actual: str) -> None:
    """Refuse a model that is neither a configured tier model nor the default — catches typo'd
    in-code model names. Operators select their own model via env (their provider + key + cost)."""
    if actual not in registry.enabled_model_names():
        raise ValueError(
            f"model {actual!r} is not a configured tier model (set LITNAV_LLM_MODEL / "
            f"LITNAV_LLM_MODEL_FRONTIER; provider={_provider()!r}). "
            f"Configured: {sorted(registry.enabled_model_names())}."
        )


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict, model: str | None = None, temperature: float = 0.0) -> dict:
    """Return a JSON dict from the configured LLM, or `fallback` when provider=none / on error."""
    _tls.cost = 0
    _tls.was_live = False
    _tls.model = None
    if _provider() == "none":
        return fallback
    actual = model or _chat_model()
    _guard(actual)
    _tls.model = actual
    try:
        import json
        response = _completion(
            model=_litellm_model(actual),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
            timeout=30,
            **_call_kwargs(),
        )
        _tls.cost = _usage_tokens(response)
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
    _guard(actual)
    _tls.model = actual
    try:
        response = _completion(
            model=_litellm_model(actual),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=30,
            **_call_kwargs(),
        )
        _tls.cost = _usage_tokens(response)
        _tls.was_live = _tls.cost > 0
        return response.choices[0].message.content or fallback
    except Exception as e:
        if _strict():
            raise LivenessError(f"complete_text failed in strict mode: {e}") from e
        return fallback


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Return one embedding vector per text, or None when offline (provider=none) / on error.
    Embeddings require an embedding-capable provider (OpenAI, Gemini, Cohere, Voyage, …). Providers
    without an embeddings API (e.g. Anthropic) return None here, and callers degrade gracefully
    (BM25-only ranking, no semantic cache)."""
    _tls.cost = 0
    _tls.was_live = False
    _tls.model = None
    if _embed_provider() == "none" or not texts:
        return None
    try:
        _tls.model = _embed_model()
        response = _embedding(model=_litellm_embed_model(_embed_model()), input=list(texts),
                              **_embed_call_kwargs())
        _tls.cost = _usage_tokens(response)
        _tls.was_live = _tls.cost > 0
        data = response.data
        return [d["embedding"] if isinstance(d, dict) else d.embedding for d in data]
    except Exception as e:
        if _strict():
            raise LivenessError(f"embed_texts failed in strict mode: {e}") from e
        return None
