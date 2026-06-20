"""Model registry — the single source of truth for which models the router may call.

Only ENABLED tiers are callable. Any other model need (including non-OpenAI providers, a
fine-tuned tutor model, a reranker, etc.) lives in RECORDED_NEEDS as documentation ONLY and is
NEVER resolvable — it cannot be called until a human promotes it into MODEL_REGISTRY.
`usd_per_1k` is a single blended per-tier rate (input+output averaged), enough for metering and
budget; a precise input/output split is a later refinement (YAGNI here).
"""
from __future__ import annotations

# Enabled tiers. usd_per_1k = blended estimate per 1,000 total tokens.
MODEL_REGISTRY: dict[str, dict] = {
    "cheap":    {"model": "gpt-4o-mini",             "usd_per_1k": 0.0004},
    "frontier": {"model": "gpt-4o",                  "usd_per_1k": 0.0050},
    "embed":    {"model": "text-embedding-3-small",   "usd_per_1k": 0.00002},
}

# Record-only: documented needs, DISABLED. Promote into MODEL_REGISTRY only on explicit approval.
RECORDED_NEEDS: list[dict] = [
    {"name": "mid", "why": "stronger QG/grading than gpt-4o-mini if a measured need appears"},
    {"name": "reranker", "why": "retrieval re-ranker beyond BM25+SPECTER, if needed"},
    {"name": "tutor-dpo-small", "why": "DPO-tuned small tutor model (cost/quality), incl. non-OpenAI"},
]


def is_enabled(tier: str) -> bool:
    return tier in MODEL_REGISTRY


def resolve_tier(tier: str) -> dict:
    """Return {model, usd_per_1k} for an ENABLED tier, else raise ValueError."""
    if tier not in MODEL_REGISTRY:
        raise ValueError(
            f"tier {tier!r} is not an enabled model. Enabled: {sorted(MODEL_REGISTRY)}. "
            f"Record-only needs (require approval): {[n['name'] for n in RECORDED_NEEDS]}."
        )
    return MODEL_REGISTRY[tier]
