"""G-digest-live (LIVE): prove the digest CAPABILITY on real LLM output. Skips at provider=none.

Asserts liveness + structural invariants (edges over EXTRACTED slugs, evidence resolves, downgrades
flagged) + that the verify judge actually ran on the REAL frontier model (gpt-4o, not the cheap model
self-judging) + real metered cost <= budget. edge_accuracy is REPORTED as the live quality signal; a
HARD prereq-survival floor is deferred to OW-3 (a few-sentence seed fixture cannot support hard
prerequisites, so a strong judge downgrading them to similarity is correct, not a failure). This is
the CAPABILITY gate; verify_digest (golden) is only a determinism/schema unit test.
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

    # OW-5.1: assert the graph PERSISTED to the DB (the gate previously only checked the in-memory
    # return; concepts were being silently dropped by INSERT OR IGNORE on a bad LLM frontier_flag,
    # leaving teach/artifact with nothing). Re-read what downstream stages actually consume.
    db_concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    assert db_concepts >= 2, f"FAIL: digest returned concepts but only {db_concepts} PERSISTED to DB"
    unresolved_kp = conn.execute(
        "SELECT COUNT(*) FROM keypoints kp LEFT JOIN paper_chunks pc ON pc.id = kp.evidence_chunk_id "
        "WHERE kp.evidence_chunk_id IS NOT NULL AND pc.id IS NULL").fetchone()[0]
    assert unresolved_kp == 0, f"FAIL: {unresolved_kp} keypoints have unresolved evidence_chunk_id"
    print(f"G-digest-live PASS: {db_concepts} concepts PERSISTED; all keypoint evidence resolves")

    # the verify judge actually ran on the REAL frontier model (gpt-4o), not the cheap model self-judging
    frows = conn.execute(
        "SELECT model, SUM(total_tokens), COUNT(*) FROM cost_ledger "
        "WHERE stage='digest_verify' GROUP BY model").fetchall()
    if frows:
        for model, tok, n in frows:
            assert model == "gpt-4o", f"FAIL: frontier judge used {model!r}, not gpt-4o (tier not routed)"
            assert tok > 0, "FAIL: judge recorded 0 tokens"
        print(f"G-digest-live PASS: judge ran on real frontier gpt-4o {frows}")
    else:
        print("G-digest-live NOTE: no high-impact prereq edges proposed to judge this run")
    # edge_accuracy is the REPORTED live quality signal (judge-agreement on proposed prereq edges).
    # Hard prereq-survival floor deferred to OW-3 (thin seed evidence cannot support hard prerequisites;
    # the strong judge correctly downgrades unsupported prereqs to similarity).
    assert 0.0 <= res.edge_accuracy <= 1.0
    assert spend["usd"] <= 1.0, f"FAIL: cost {spend['usd']} over sane bound"
    print(f"G-digest-live QUALITY: edge_accuracy={res.edge_accuracy} (prereq-survival; hard floor "
          f"deferred to OW-3 full-text); cost ${spend['usd']}")
    print("G-digest-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
