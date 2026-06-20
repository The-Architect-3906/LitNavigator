"""G-discover-live (LIVE): prove find-sources discovers real sources AND that digest, fed REAL
full text discovered live, can build edges on rich evidence (the A1 re-evaluation). Skips offline."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.discover.contract import DiscoverInput
from litnav.discover import find_sources
from litnav.discover.rank import _norm_title
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.llm import client as llm_client

_GOAL = "how do LLM agents reason and act with tools"
_BUDGET = 60000
_EMPTY = {"concepts": [], "keypoints": [], "prereq_edges": [], "similarity_edges": [],
          "quiz_seeds": [], "judge_labels": {}}


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-discover-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    conn = sqlite3.connect(":memory:"); init_db(conn)

    res = find_sources.find(DiscoverInput(_GOAL, k=6), conn=conn, session_id="disc", budget=_BUDGET)
    spend = cost_repo.session_spend(conn, "disc")
    assert spend["tokens"] > 0, "FAIL: no metered discover spend (intent/rerank didn't run live)"
    assert len(res.sources) >= 3, f"FAIL: <3 sources ({len(res.sources)})"
    for s in res.sources:
        assert s.title and s.url, f"FAIL: source missing title/url {s}"
        assert 0.0 <= s.authority_score <= 1.0
    titles = [_norm_title(s.title) for s in res.sources]
    assert len(titles) == len(set(titles)), "FAIL: dedup did not hold"
    withft = [s for s in res.sources if s.chunks and sum(len(ch) for ch in s.chunks) > 200]
    assert withft, "FAIL: no source got real multi-sentence full text"
    print(f"G-discover-live PASS: {len(res.sources)} sources, intent={res.intent_used}, "
          f"{len(withft)} with full text, discover spend={spend['usd']}")

    # ---- A1 re-evaluation: digest the richest discovered source LIVE ----
    top = max(withft, key=lambda s: sum(len(ch) for ch in s.chunks))
    di = DigestInput(domain_key=_GOAL,
                     sources=[SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                     target_slugs=[])
    dres = pipeline.digest(di, conn=conn, candidate=_EMPTY, session_id="dg", budget=_BUDGET)
    assert llm_client.was_live(), "FAIL: digest did not run live"
    assert len(dres.concepts) >= 2, f"FAIL: digest <2 concepts on rich evidence ({len(dres.concepts)})"
    dspend = cost_repo.session_spend(conn, "dg")
    # REPORT (do not hard-gate) the A1 signal: edges + survival on RICH evidence vs the 3-sentence 0.0
    print(f"G-discover-live A1-REPORT: source={top.title!r} ({sum(len(c) for c in top.chunks)} chars) "
          f"-> {len(dres.concepts)} concepts, {len(dres.edges)} edges "
          f"({sum(1 for e in dres.edges if e['edge_type']=='prerequisite')} prereq survived), "
          f"edge_accuracy={dres.edge_accuracy}, digest spend={dspend['usd']}")
    print("--- COST ledger (discover + digest) ---")
    for row in conn.execute("SELECT stage,tier,model,SUM(total_tokens),ROUND(SUM(usd),6),COUNT(*) "
                            "FROM cost_ledger GROUP BY stage,tier,model ORDER BY stage,tier"):
        print("  ", tuple(row))
    print("G-discover-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
