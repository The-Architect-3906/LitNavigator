"""G-liveness (LIVE): prove a real LLM call is distinguishable from a silent fallback.

Run with a real provider:  LITNAV_LLM_PROVIDER=openai  python -m litnav.evaluation.verify_liveness
At provider=none it SKIPS with a clear message (it cannot test liveness offline).
"""
from __future__ import annotations

import os
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, client as llm_client
from litnav.llm.client import LivenessError


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-liveness SKIP: set LITNAV_LLM_PROVIDER=openai to run this LIVE gate.")
        return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    conn = sqlite3.connect(":memory:"); init_db(conn)

    # 1) a real call registers as live with metered tokens
    out = router.complete_text("Reply with the single word: pong.", tier="cheap",
                               stage="liveness", session_id="live", conn=conn, max_tokens=8)
    assert llm_client.was_live(), "G-liveness FAIL: real call did not register live (tokens=0/fallback)"
    spend = cost_repo.session_spend(conn, "live")
    assert spend["tokens"] > 0, "G-liveness FAIL: no tokens metered on a live call"
    print(f"G-liveness PASS: live call ok (reply={out!r}, tokens={spend['tokens']}, usd={spend['usd']})")

    # 2) a forced provider error RAISES (not silent fallback)
    saved = os.environ.get("LITNAV_LLM_MODEL")
    os.environ["LITNAV_LLM_MODEL"] = "this-model-does-not-exist-zzz"
    try:
        router.complete_text("x", tier="cheap", stage="liveness", session_id="live2",
                             conn=conn, fallback="fb")
        print("G-liveness FAIL: bad model did NOT raise in strict mode (silent fallback)")
        return 1
    except LivenessError:
        print("G-liveness PASS: strict mode raised on provider error (no silent fallback)")
    finally:
        if saved is None:
            os.environ.pop("LITNAV_LLM_MODEL", None)
        else:
            os.environ["LITNAV_LLM_MODEL"] = saved

    print("G-liveness: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
