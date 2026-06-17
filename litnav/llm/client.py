"""LLM + embedding client.

Provider is selected by LITNAV_LLM_PROVIDER:
  - none   (default): no calls; complete_json returns the caller's fallback, embed_texts -> None.
  - openai           : OpenAI API (chat = LITNAV_LLM_MODEL, default gpt-4o-mini;
                       embeddings = LITNAV_EMBED_MODEL, default text-embedding-3-small).
  - qwen             : DashScope OpenAI-compatible endpoint (model qwen-plus).

Key comes from LITNAV_LLM_API_KEY (or OPENAI_API_KEY). Never hard-coded.
Every caller passes a deterministic fallback, so the system always runs offline.
"""
from __future__ import annotations

import os
import threading

# Per-thread token cost: each calling thread sees its own counter so concurrent
# sessions do not bleed cost into each other's records.
_tls = threading.local()


def last_token_cost() -> int:
    """Token cost of the most recent call on this thread (0 when offline / no usage)."""
    return getattr(_tls, "cost", 0)


def _provider() -> str:
    return os.getenv("LITNAV_LLM_PROVIDER", "none")


def _api_key() -> str:
    return os.getenv("LITNAV_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")


def _chat_model() -> str:
    return os.getenv("LITNAV_LLM_MODEL", "gpt-4o-mini")


def _embed_model() -> str:
    return os.getenv("LITNAV_EMBED_MODEL", "text-embedding-3-small")


def _client():
    from openai import OpenAI
    if _provider() == "qwen":
        return OpenAI(api_key=_api_key(),
                      base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    base = os.getenv("LITNAV_LLM_BASE_URL")  # optional (Azure/proxy/self-hosted)
    return OpenAI(api_key=_api_key(), base_url=base) if base else OpenAI(api_key=_api_key())


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict) -> dict:
    """Return a JSON dict from the configured LLM, or `fallback` when provider=none / on error."""
    _tls.cost = 0
    if _provider() == "none":
        return fallback
    try:
        import json
        model = "qwen-plus" if _provider() == "qwen" else _chat_model()
        response = _client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=30,
        )
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        return json.loads(response.choices[0].message.content)
    except Exception:
        return fallback


def complete_text(prompt: str, *, fallback: str, max_tokens: int = 400) -> str:
    """Return a free-text completion (e.g. a grounded teaching turn), or `fallback` offline/on error."""
    _tls.cost = 0
    if _provider() == "none":
        return fallback
    try:
        model = "qwen-plus" if _provider() == "qwen" else _chat_model()
        response = _client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=30,
        )
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        return response.choices[0].message.content or fallback
    except Exception:
        return fallback


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Return one embedding vector per text, or None when offline (provider=none) / on error."""
    _tls.cost = 0
    if _provider() == "none" or not texts:
        return None
    try:
        response = _client().embeddings.create(model=_embed_model(), input=list(texts))
        try:
            _tls.cost = int(response.usage.total_tokens or 0)
        except Exception:
            pass
        return [d.embedding for d in response.data]
    except Exception:
        return None
