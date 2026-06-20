"""G-digest-live (LIVE): prove the digest CAPABILITY on real LLM output. Skips at provider=none.

Asserts liveness + structural invariants (edges over EXTRACTED slugs, evidence resolves, downgrades
flagged) + a quality threshold + real metered cost. This is the CAPABILITY gate; verify_digest (golden)
is only a determinism/schema unit test.
"""
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path
from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.llm import client as llm_client

_FIX = Path("data/seed/digest_sources_fixture.json")
_FLOOR = 0.5
_BUDGET = 20000


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-digest-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    raw = json.loads(_FIX.read_text(encoding="utf-8"))
    di = DigestInput(raw["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in raw["sources"]], raw.get("target_slugs", []))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    res = pipeline.digest(di, conn=conn, candidate=raw["candidate"], session_id="dl", budget=_BUDGET)

    assert llm_client.was_live(), "FAIL: digest did not run live"
    spend = cost_repo.session_spend(conn, "dl")
    assert spend["tokens"] > 0, "FAIL: no real spend recorded"
    print(f"G-digest-live PASS: live (tokens={spend['tokens']}, usd={spend['usd']})")

    slugs = {c["slug"] for c in res.concepts}
    assert len(slugs) >= 2, f"FAIL: <2 concepts extracted ({slugs})"
    for e in res.edges:
        assert e["prereq_slug"] in slugs and e["target_slug"] in slugs, f"FAIL: edge off-slugs {e}"
    assert len(res.edges) > 0, "FAIL: zero edges from >=2 concepts (the OW-2 bug)"
    for e in res.edges:
        for cid in e["evidence"]:
            assert repo.get_chunk_text(conn, cid), f"FAIL: evidence {cid} resolves empty"
    for uv in res.unverified_edges:
        assert uv["edge_type"] == "similarity", "FAIL: unverified edge not downgraded"
    print(f"G-digest-live PASS: {len(slugs)} concepts, {len(res.edges)} edges, all grounded")

    assert res.edge_accuracy >= _FLOOR, f"FAIL: edge_accuracy {res.edge_accuracy} < floor {_FLOOR}"
    assert spend["usd"] <= 1.0, f"FAIL: cost {spend['usd']} over sane bound"
    print(f"G-digest-live PASS: edge_accuracy={res.edge_accuracy} >= {_FLOOR}; cost ${spend['usd']}")
    print("G-digest-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
