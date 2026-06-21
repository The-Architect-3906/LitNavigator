"""G-cost: prove the cost spine — metering records spend, the budget cap fires, and a
record-only model cannot be called. Runs fully offline + with a monkeypatched live provider.
"""
from __future__ import annotations

import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, BudgetExceeded
from litnav.llm import client as llm_client


def main() -> int:
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    # 1) Offline call records a 0-cost row (determinism preserved).
    import os
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    router.complete_text("x", tier="cheap", stage="teach", session_id="s", conn=conn, fallback="fb")
    assert cost_repo.session_spend(conn, "s")["tokens"] == 0
    print("G-cost PASS: offline call recorded at 0 cost")

    # 2) A record-only model cannot be called.
    try:
        router.complete_text("x", tier="reranker", stage="teach", session_id="s", conn=conn,
                             fallback="fb")
        raise SystemExit("G-cost FAIL: record-only model was callable")
    except ValueError:
        print("G-cost PASS: record-only model refused")

    # 3) Metering + budget cap fire with a (faked) live provider.
    llm_client.complete_text = lambda *a, **k: "live"
    llm_client.last_token_cost = lambda: 700
    conn2 = sqlite3.connect(":memory:"); init_db(conn2)
    router.complete_text("a", tier="cheap", stage="teach", session_id="b", conn=conn2,
                         fallback="fb", budget=1000)
    assert cost_repo.session_spend(conn2, "b")["tokens"] == 700
    try:
        router.complete_text("b", tier="cheap", stage="teach", session_id="b", conn=conn2,
                             fallback="fb", budget=1000)
        raise SystemExit("G-cost FAIL: budget did not fire")
    except BudgetExceeded:
        print("G-cost PASS: metering + budget cap fired")

    print("G-cost: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
