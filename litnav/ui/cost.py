"""Per-session LLM cost, for the efficiency panel.

token_cost is the total tokens recorded per tutor turn (0 offline). We estimate USD with a
single blended gpt-4o-mini rate (input $0.15/1M, output $0.60/1M -> ~$0.0004/1k blended).
Offline (provider=none) every turn costs 0, so a fully offline session shows $0.
"""
from __future__ import annotations

import sqlite3

_USD_PER_1K_TOKENS = 0.0004  # blended gpt-4o-mini estimate


def session_cost(conn: sqlite3.Connection, session_id: str) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(token_cost), 0) FROM tutor_turns WHERE session_id=?",
        (session_id,),
    ).fetchone()
    tokens = int(row[0] or 0)
    return {"tokens": tokens, "usd": round(tokens / 1000 * _USD_PER_1K_TOKENS, 5)}
