"""G-cost-live (LIVE): prove metering + budget cap work on REAL spend. Skips at provider=none."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, client as llm_client, BudgetExceeded


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-cost-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    conn = sqlite3.connect(":memory:"); init_db(conn)

    router.complete_text("Say hi.", tier="cheap", stage="costlive", session_id="cl",
                         conn=conn, fallback="x", max_tokens=8, budget=100000)
    assert llm_client.was_live(), "G-cost-live FAIL: call not live"
    sp = cost_repo.session_spend(conn, "cl")
    assert sp["tokens"] > 0 and sp["usd"] > 0, "G-cost-live FAIL: no real spend recorded"
    print(f"G-cost-live PASS: live spend tokens={sp['tokens']} usd={sp['usd']}")

    v = router.embed_texts(["alpha", "beta"], stage="costlive", session_id="cl", conn=conn)
    assert v is not None, "G-cost-live FAIL: embed returned None live"
    print("G-cost-live PASS: live embed metered")

    fired = False
    try:
        for _ in range(50):
            router.complete_text("Write two sentences about software agents.", tier="cheap",
                                 stage="costlive", session_id="cap", conn=conn, fallback="x",
                                 max_tokens=64, budget=120)
    except BudgetExceeded:
        fired = True
    assert fired, "G-cost-live FAIL: budget cap never fired on real spend"
    print("G-cost-live PASS: budget cap fired on real spend")
    print("G-cost-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
