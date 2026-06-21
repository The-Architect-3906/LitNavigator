"""G-live-digest (opt-in LIVE): run the real extract -> edges -> verify pipeline N times and assert the
invariants the offline suite and the shallow `edges>0` check miss — the kp_id / objective regression
class that was 'green offline, broken live'.

Catches:
  - kp_id bug: the extractor silently dropped int-id keypoints live -> 0 keypoints / no objectives.
  - placeholder objectives: fallback to candidate's "explain X" instead of real learning objectives.

Run: LITNAV_LIVE_GATES=1 LITNAV_LLM_PROVIDER=openai LITNAV_LLM_API_KEY=... \
     .venv/bin/python -m litnav.evaluation.verify_live_digest
(.env is loaded automatically; SKIPs cleanly if not opted in.)
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from litnav.config import load_dotenv
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.evaluation.live_harness import Gate, k_of_n, live_enabled

_FIX = Path("data/seed/digest_sources_fixture.json")
_N = 4               # runs per check — small, budget-capped
_BUDGET = 30000
_MIN_OBJ_WORDS = 6   # a real objective is a sentence; the kp_id-fallback placeholders were 2-3 words


def _run_once(raw: dict):
    di = DigestInput(raw["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in raw["sources"]], raw.get("target_slugs", []))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    try:
        return pipeline.digest(di, conn=conn, candidate=raw["candidate"], session_id="lg", budget=_BUDGET)
    except Exception as e:  # a strict-mode crash is a real failure the gate should surface
        return e


def main() -> int:
    load_dotenv()
    gate = Gate("G-live-digest")
    ok, why = live_enabled()
    if not ok:
        return gate.skip(why)
    os.environ["LITNAV_LLM_STRICT"] = "1"   # never silently fall back — that is what hides live bugs

    raw = json.loads(_FIX.read_text(encoding="utf-8"))
    runs = [_run_once(raw) for _ in range(_N)]
    done = [r for r in runs if not isinstance(r, Exception)]
    gate.hard("all runs completed (no strict-mode crash)", len(done) == _N,
              f"{len(done)}/{_N}" + (f"; err={runs[0]!r}" if len(done) < _N else ""))
    if not done:
        return gate.finish()

    # 1) keypoints survive live (the kp_id bug zeroed them; offline never saw it)
    c, n = k_of_n(done, lambda r: len(r.concepts) > 0 and len(r.keypoints) >= len(r.concepts))
    gate.hard("keypoints >= #concepts, every run", c == n, f"{c}/{n}")

    # 2) objectives are real sentences, not placeholders ("explain ReAct")
    def rich(r):
        return bool(r.keypoints) and all(
            len((k.get("objective") or "").split()) >= _MIN_OBJ_WORDS for k in r.keypoints)
    c, n = k_of_n(done, rich)
    gate.hard(f"every objective >= {_MIN_OBJ_WORDS} words, every run", c == n, f"{c}/{n}")

    # 3) non-empty graph — advisory: a tiny fixture has a known 0-edge variance; tracked, not yet a hard gate
    c, n = k_of_n(done, lambda r: len(r.edges) >= 1)
    gate.advisory("runs producing >=1 edge", f"{c}/{n}")

    sample = next((r.keypoints[0].get("objective") for r in done if r.keypoints), None)
    if sample:
        gate.advisory("sample objective", repr(sample)[:110])
    return gate.finish()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
