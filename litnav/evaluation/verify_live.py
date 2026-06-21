"""verify_live — run ALL opt-in LIVE gates (digest, tutor, prereq) in one command.

These run the REAL LLM path and assert invariants the offline suite can't (it replays the deterministic
candidate, so it's blind to live-only bugs). SKIPs cleanly unless LITNAV_LIVE_GATES=1 and a key is set,
so default CI stays offline/$0. Run pre-merge for digest/tutor changes. Non-zero exit if any gate fails.

Run: LITNAV_LIVE_GATES=1 LITNAV_LLM_PROVIDER=openai LITNAV_LLM_API_KEY=... \
     .venv/bin/python -m litnav.evaluation.verify_live
"""
from __future__ import annotations

from litnav.config import load_dotenv
from litnav.evaluation.live_harness import live_enabled
from litnav.evaluation import verify_live_digest, verify_live_tutor, verify_live_prereq


def main() -> int:
    load_dotenv()
    ok, why = live_enabled()
    if not ok:
        print(f"verify_live SKIP: {why}")
        return 0
    rc = 0
    for mod in (verify_live_digest, verify_live_tutor, verify_live_prereq):
        rc |= mod.main()
        print()
    print("verify_live: ALL PASS" if rc == 0 else "verify_live: FAILURES ABOVE — see gate output")
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
