"""Opt-in LIVE gate harness — run the REAL LLM path and assert invariants the offline fallback cannot
fake. The offline suite (pytest, verify_m0..m3) replays the deterministic candidate, so it is blind to
live-only bugs (the kp_id keypoint drop, the starved prereq judge, grading/mastery on the real model).
These gates close that blind spot.

Default CI stays offline and $0: a gate runs ONLY when `LITNAV_LIVE_GATES=1` and an API key is set;
otherwise it SKIPs (exit 0). Designed for LLM non-determinism — run a check N times and assert k-of-N
(k=N for must-always-hold invariants, k<N for probabilistic ones), over ranges/structure/direction,
never exact values.
"""
from __future__ import annotations

import os


def live_enabled() -> tuple[bool, str]:
    """(enabled, reason-if-not). Opt-in AND key-gated so the default suite is untouched and $0."""
    if os.getenv("LITNAV_LIVE_GATES") != "1":
        return False, "LITNAV_LIVE_GATES != 1 (live gates are opt-in)"
    if not (os.getenv("LITNAV_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return False, "no LLM API key set"
    return True, ""


def k_of_n(results: list, pred) -> tuple[int, int]:
    """Return (count satisfying pred, n). Use for k-of-N assertions over N live runs."""
    return sum(1 for r in results if pred(r)), len(results)


class Gate:
    """Collects checks, prints a report, returns an exit code. `hard` checks fail the gate;
    `advisory` lines are reported but never fail it (use for known-variance signals)."""

    def __init__(self, name: str):
        self.name = name
        self.failed = False
        self._lines: list[str] = []

    def hard(self, label: str, passed: bool, detail: str = "") -> None:
        self._lines.append(f"  [{'PASS' if passed else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
        if not passed:
            self.failed = True

    def advisory(self, label: str, detail: str = "") -> None:
        self._lines.append(f"  [info] {label}" + (f"  ({detail})" if detail else ""))

    def skip(self, reason: str) -> int:
        print(f"{self.name} SKIP: {reason}")
        return 0

    def finish(self) -> int:
        print(f"== {self.name} ==")
        for ln in self._lines:
            print(ln)
        print(f"{'FAIL' if self.failed else 'PASS'}: {self.name}")
        return 1 if self.failed else 0
