"""Cost ledger: persist and total per-session LLM spend (the open-world metering store)."""
from __future__ import annotations

import datetime as _dt
import sqlite3


def record_cost(conn: sqlite3.Connection, *, session_id: str | None, stage: str, tier: str,
                model: str, total_tokens: int, usd: float, cache_hit: bool = False) -> None:
    """Append one metered call to cost_ledger. ts is UTC ISO-8601."""
    conn.execute(
        "INSERT INTO cost_ledger (session_id, ts, stage, tier, model, total_tokens, usd, cache_hit) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (session_id, _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"), stage, tier, model,
         int(total_tokens), float(usd), 1 if cache_hit else 0),
    )
    conn.commit()


def session_spend(conn: sqlite3.Connection, session_id: str) -> dict:
    """Total tokens and USD recorded for a session (0/0.0 when none)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(usd), 0.0) "
        "FROM cost_ledger WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return {"tokens": int(row[0] or 0), "usd": round(float(row[1] or 0.0), 6)}
