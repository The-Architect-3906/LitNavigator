"""Model registry — default tiers + per-tier env overrides; the metering source of truth.

Three tiers (cheap / frontier / embed) drive every routed call. The defaults are OpenAI models, so
dev/eval and the offline demo stay on them with zero config. But LitNavigator is **provider-agnostic**:
an operator can point it at ANY OpenAI-compatible provider — OpenAI, DeepSeek, Groq, OpenRouter,
Together, Ollama, Azure, vLLM, a local server, etc. — by overriding the per-tier model via env. The
chosen base_url + key (see `llm/client.py`) plus these models then drive every call. `usd_per_1k` is a
blended per-tier rate for metering/budget and is likewise env-overridable so cost stays accurate on
other providers' pricing.

Env overrides (all optional):
  LITNAV_LLM_MODEL            → cheap-tier chat model (the default chat model)
  LITNAV_LLM_MODEL_FRONTIER   → frontier-tier chat model (set equal to cheap for single-model providers)
  LITNAV_EMBED_MODEL          → embedding model
  LITNAV_LLM_USD_PER_1K / _FRONTIER, LITNAV_EMBED_USD_PER_1K → blended rates for metering

`RECORDED_NEEDS` documents capabilities that are NOT wired (e.g. a reranker, a fine-tuned tutor
model). They remain non-resolvable until actually implemented — this is documentation, not a denylist.
"""
from __future__ import annotations

import os

# Built-in defaults (OpenAI). Used when the matching env var is unset — so dev/eval stay on these.
_DEFAULTS: dict[str, dict] = {
    "cheap":    {"model": "gpt-4o-mini",             "usd_per_1k": 0.0004},
    "frontier": {"model": "gpt-4o",                  "usd_per_1k": 0.0050},
    "embed":    {"model": "text-embedding-3-small",   "usd_per_1k": 0.00002},
}

# Convenience default chat model per provider when LITNAV_LLM_MODEL is unset (e.g. qwen back-compat).
_PROVIDER_DEFAULT_CHAT: dict[str, str] = {"qwen": "qwen-plus"}

# Snapshot of the defaults for any external reference; prefer the functions below (they read env live).
MODEL_REGISTRY: dict[str, dict] = {k: dict(v) for k, v in _DEFAULTS.items()}

# Record-only: documented capabilities NOT wired into the pipeline (not a model denylist).
RECORDED_NEEDS: list[dict] = [
    {"name": "mid", "why": "stronger QG/grading than gpt-4o-mini if a measured need appears"},
    {"name": "reranker", "why": "retrieval re-ranker beyond BM25+SPECTER, if needed"},
    {"name": "tutor-dpo-small", "why": "DPO-tuned small tutor model (cost/quality), incl. non-OpenAI"},
]


def _env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


def _rate(name: str, default: float) -> float:
    v = _env(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _cheap_model() -> str:
    return (_env("LITNAV_LLM_MODEL")
            or _PROVIDER_DEFAULT_CHAT.get(os.getenv("LITNAV_LLM_PROVIDER", "none"))
            or _DEFAULTS["cheap"]["model"])


def _frontier_model() -> str:
    # Explicit override wins; else the default frontier. A single-model provider points both tiers at
    # one model by setting LITNAV_LLM_MODEL_FRONTIER to the same value as LITNAV_LLM_MODEL.
    return _env("LITNAV_LLM_MODEL_FRONTIER") or _DEFAULTS["frontier"]["model"]


def _embed_model() -> str:
    return _env("LITNAV_EMBED_MODEL") or _DEFAULTS["embed"]["model"]


def _registry() -> dict[str, dict]:
    """Resolve the live tier table from defaults + env overrides (read at call time)."""
    return {
        "cheap":    {"model": _cheap_model(),
                     "usd_per_1k": _rate("LITNAV_LLM_USD_PER_1K", _DEFAULTS["cheap"]["usd_per_1k"])},
        "frontier": {"model": _frontier_model(),
                     "usd_per_1k": _rate("LITNAV_LLM_USD_PER_1K_FRONTIER", _DEFAULTS["frontier"]["usd_per_1k"])},
        "embed":    {"model": _embed_model(),
                     "usd_per_1k": _rate("LITNAV_EMBED_USD_PER_1K", _DEFAULTS["embed"]["usd_per_1k"])},
    }


def enabled_model_names() -> set[str]:
    """The model name strings currently callable (the resolved per-tier models)."""
    return {spec["model"] for spec in _registry().values()}


def is_enabled(tier: str) -> bool:
    return tier in _registry()


def resolve_tier(tier: str) -> dict:
    """Return {model, usd_per_1k} for a known tier, else raise ValueError."""
    reg = _registry()
    if tier not in reg:
        raise ValueError(
            f"tier {tier!r} is not a known tier. Tiers: {sorted(reg)}. "
            f"Record-only needs (not wired): {[n['name'] for n in RECORDED_NEEDS]}."
        )
    return reg[tier]
