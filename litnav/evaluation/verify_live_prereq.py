"""G-live-prereq (opt-in LIVE): prove the prerequisite path end-to-end on a corpus that actually HAS a
dependency chain. This is the honest close-out of D3 ('prereqs all downgraded live').

D3 was NOT a judge bug: the starved judge (bare slugs + chunk-ids) was fixed to read concept
descriptions + evidence text, and the only fixture available was sibling-heavy (ReAct / Tool use /
Reflexion have no necessary prereqs, so '0 prereqs' there is correct). On a real chain
(tokenization -> embeddings -> attention -> transformer) the judge must KEEP the prerequisites.

Run: LITNAV_LIVE_GATES=1 LITNAV_LLM_PROVIDER=openai LITNAV_LLM_API_KEY=... \
     .venv/bin/python -m litnav.evaluation.verify_live_prereq
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

_FIX = Path("data/seed/digest_prereq_fixture.json")
_N = 4
_BUDGET = 30000


def _run_once(raw: dict):
    di = DigestInput(raw["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in raw["sources"]], raw.get("target_slugs", []))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    try:
        return pipeline.digest(di, conn=conn, candidate=raw["candidate"], session_id="lp", budget=_BUDGET)
    except Exception as e:
        return e


def main() -> int:
    load_dotenv()
    gate = Gate("G-live-prereq")
    ok, why = live_enabled()
    if not ok:
        return gate.skip(why)
    os.environ["LITNAV_LLM_STRICT"] = "1"

    raw = json.loads(_FIX.read_text(encoding="utf-8"))
    runs = [_run_once(raw) for _ in range(_N)]
    done = [r for r in runs if not isinstance(r, Exception)]
    gate.hard("all runs completed", len(done) == _N,
              f"{len(done)}/{_N}" + (f"; err={runs[0]!r}" if len(done) < _N else ""))
    if not done:
        return gate.finish()

    def _prereqs(r):
        return [e for e in r.edges if e["edge_type"] == "prerequisite"]

    # D3 close-out: on a real dependency chain, prerequisites must SURVIVE the verify judge.
    c, n = k_of_n(done, lambda r: len(_prereqs(r)) >= 1)
    gate.hard("prerequisites survive (>=1 prereq edge per run)", c * 4 >= n * 3,  # >=75% of runs
              f"{c}/{n}")

    # quality signal: how many of the 3 chain edges survive on average, and judge agreement
    total = sum(len(_prereqs(r)) for r in done)
    gate.advisory("avg surviving prereqs/run", f"{total / len(done):.2f}")
    accs = [r.edge_accuracy for r in done]
    gate.advisory("edge_accuracy (judge agreement)", f"min={min(accs)} mean={sum(accs) / len(accs):.2f}")
    sample = next((e for r in done for e in _prereqs(r)), None)
    if sample:
        gate.advisory("sample prereq", f"{sample['prereq_slug']}->{sample['target_slug']} conf={sample['confidence']}")
    return gate.finish()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
