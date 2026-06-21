"""Per-session LLM cost, for the efficiency panel.

The authoritative source is `cost_ledger` — every metered LLM/embedding call (discover, digest,
teach, grade, artifact) is written there with real token counts and USD by the router. Offline
(provider=none) those rows are $0, so a fully offline session shows $0. We fall back to the legacy
per-turn `tutor_turns.token_cost` (estimated) only when the ledger has nothing for the session.
"""
from __future__ import annotations

import sqlite3

_USD_PER_1K_TOKENS = 0.0004  # blended gpt-4o-mini estimate (legacy fallback only)


def session_cost(conn: sqlite3.Connection, session_id: str) -> dict:
    # Primary: the real metered ledger (covers discover/digest/teach/grade/artifact).
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(usd), 0) "
            "FROM cost_ledger WHERE session_id=?",
            (session_id,),
        ).fetchone()
        tokens, usd = int(row[0] or 0), float(row[1] or 0.0)
        if tokens or usd:
            return {"tokens": tokens, "usd": round(usd, 5)}
    except sqlite3.OperationalError:
        pass  # no ledger table (older DB) — fall back below
    # Fallback: legacy per-turn token field with a blended rate estimate.
    row = conn.execute(
        "SELECT COALESCE(SUM(token_cost), 0) FROM tutor_turns WHERE session_id=?",
        (session_id,),
    ).fetchone()
    tokens = int(row[0] or 0)
    return {"tokens": tokens, "usd": round(tokens / 1000 * _USD_PER_1K_TOKENS, 5)}
