"""BUG A3/B5: build_trace total_token_cost must come from cost_ledger, not
tutor_turns.token_cost + decisions.token_cost (which are always 0 on the live path)."""
import sqlite3

from litnav.storage.cost_repo import record_cost
from litnav.storage.schema import init_db
from litnav.ui.trace import build_trace


def _make_session(conn: sqlite3.Connection) -> str:
    sid = "test-cost-session-001"
    conn.execute(
        "INSERT INTO sessions (id, topic, status) VALUES (?, ?, ?)",
        (sid, "Test Topic", "active"),
    )
    conn.commit()
    return sid


def test_total_token_cost_reads_cost_ledger():
    """total_token_cost in build_trace must reflect cost_ledger rows, not the per-turn fields."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    sid = _make_session(conn)

    # Insert a real metered cost into cost_ledger (live path pattern).
    record_cost(
        conn,
        session_id=sid,
        stage="teach",
        tier="cheap",
        model="gpt-4o-mini",
        total_tokens=500,
        usd=0.0002,
    )

    trace = build_trace(conn, sid)
    assert trace["total_token_cost"] > 0, (
        f"expected total_token_cost > 0 from cost_ledger, got {trace['total_token_cost']}"
    )
