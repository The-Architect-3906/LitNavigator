import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_record_and_total_spend():
    conn = _conn()
    cost_repo.record_cost(conn, session_id="s1", stage="teach", tier="cheap",
                          model="gpt-4o-mini", total_tokens=1000, usd=0.0004, cache_hit=False)
    cost_repo.record_cost(conn, session_id="s1", stage="assess", tier="frontier",
                          model="gpt-4o", total_tokens=500, usd=0.0025, cache_hit=False)
    cost_repo.record_cost(conn, session_id="other", stage="teach", tier="cheap",
                          model="gpt-4o-mini", total_tokens=9999, usd=9.9, cache_hit=False)

    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 1500
    assert round(spend["usd"], 4) == 0.0029     # 0.0004 + 0.0025, only session s1


def test_session_spend_empty_is_zero():
    conn = _conn()
    assert cost_repo.session_spend(conn, "nobody") == {"tokens": 0, "usd": 0.0}
