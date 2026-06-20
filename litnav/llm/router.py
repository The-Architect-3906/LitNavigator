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
    tokens = int(llm_client.last_token_cost() or 0)
    usd = round(tokens / 1000 * usd_per_1k, 6)
    if conn is not None:
        cost_repo.record_cost(conn, session_id=session_id, stage=stage, tier=tier, model=model,
                              total_tokens=tokens, usd=usd, cache_hit=False)
    if budget is not None and conn is not None and session_id is not None:
        if cost_repo.session_spend(conn, session_id)["tokens"] >= budget:
            raise BudgetExceeded(
                f"session {session_id!r} reached token budget {budget} (stage={stage})")


def complete_text(prompt: str, *, tier: str, stage: str, fallback: str,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  max_tokens: int = 400, budget: int | None = None) -> str:
    spec = registry.resolve_tier(tier)               # raises if disabled/unknown -- before any call
    out = llm_client.complete_text(prompt, fallback=fallback, max_tokens=max_tokens)
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out


def complete_json(prompt: str, *, tier: str, stage: str, fallback: dict,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  schema_hint: str = "", budget: int | None = None) -> dict:
    spec = registry.resolve_tier(tier)
    out = llm_client.complete_json(prompt, schema_hint=schema_hint, fallback=fallback)
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out
