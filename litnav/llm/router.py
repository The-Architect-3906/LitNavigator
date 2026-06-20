"""Router -- the single metered chokepoint for every open-world LLM call.

Resolves a tier against the registry (refusing disabled/record-only models), calls the underlying
client, reads the per-call token cost, computes USD from the tier rate, and writes a cost_ledger
row. Offline (provider=none) the client returns the caller's fallback with 0 token cost, so a
0-cost row is recorded and budgets are never tripped -- determinism preserved.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.llm import registry
from litnav.storage import cost_repo


class BudgetExceeded(RuntimeError):
    """Raised when a session's recorded spend has reached its token budget."""


def _meter(*, conn, session_id, stage, tier, model, usd_per_1k, budget):
    """Record this call's cost; enforce the budget AFTER recording. Returns nothing."""
    import warnings
    tokens = int(llm_client.last_token_cost() or 0)
    usd = round(tokens / 1000 * usd_per_1k, 6)
    actual_model = llm_client.last_model() or model
    if conn is not None:
        cost_repo.record_cost(conn, session_id=session_id, stage=stage, tier=tier,
                              model=actual_model, total_tokens=tokens, usd=usd, cache_hit=False)
    if budget is not None and conn is not None and session_id is not None:
        spent = cost_repo.session_spend(conn, session_id)["tokens"]
        if 0.8 * budget <= spent < budget:
            warnings.warn(
                f"session {session_id!r} at {spent}/{budget} tokens (>=80% of budget, stage={stage})",
                stacklevel=2,
            )
        if spent >= budget:
            raise BudgetExceeded(
                f"session {session_id!r} reached token budget {budget} (stage={stage})")


def complete_text(prompt: str, *, tier: str, stage: str, fallback: str,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  max_tokens: int = 400, budget: int | None = None) -> str:
    spec = registry.resolve_tier(tier)               # raises if disabled/unknown -- before any call
    out = llm_client.complete_text(prompt, fallback=fallback, max_tokens=max_tokens, model=spec["model"])
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out


def complete_json(prompt: str, *, tier: str, stage: str, fallback: dict,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  schema_hint: str = "", budget: int | None = None) -> dict:
    spec = registry.resolve_tier(tier)
    out = llm_client.complete_json(prompt, schema_hint=schema_hint, fallback=fallback, model=spec["model"])
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out


def embed_texts(texts: list[str], *, stage: str, tier: str = "embed",
                session_id: str | None = None, conn: sqlite3.Connection | None = None,
                budget: int | None = None) -> list[list[float]] | None:
    """Metered embedding call. Returns one vector per text, or None offline (provider=none).
    Records a cost_ledger row (0 tokens offline) and enforces the budget, exactly like the
    completion paths -- so digest's embeddings count toward spend."""
    spec = registry.resolve_tier(tier)               # raises if disabled/unknown
    out = llm_client.embed_texts(texts)
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out


def over_budget_fraction(conn: sqlite3.Connection, session_id: str, budget: int | None) -> float:
    """Return the fraction of budget consumed by session_id (0.0 if budget is falsy)."""
    if not budget:
        return 0.0
    return round(cost_repo.session_spend(conn, session_id)["tokens"] / budget, 4)
