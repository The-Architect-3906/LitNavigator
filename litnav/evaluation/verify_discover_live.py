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
    # ---- OW-3.1 (A6): multilingual goal -> English search query, live ----
    from litnav.discover import query as dquery, relevance as drel
    from litnav.discover.contract import Source
    zh = "给我一个关于 CRISPR 基因编辑的快速概览"
    eq = dquery.to_search_query(zh, conn=conn, session_id="disc", budget=_BUDGET)
    assert eq and eq != zh, f"FAIL: query not normalized: {eq!r}"
    assert sum(1 for ch in eq if ord(ch) < 128) >= len(eq) * 0.8, f"FAIL: not English-ish: {eq!r}"
    print(f"G-discover-live PASS (A6): {zh!r} -> {eq!r}")

    # ---- OW-3.1 (A5): relevance gate drops an off-topic source, live ----
    cand = [Source("web", "raft", "u", "Raft consensus algorithm",
                   abstract="A understandable consensus algorithm for managing a replicated log."),
            Source("wikipedia", "mega", "u", "Megalopolis (film)",
                   abstract="A 2024 American epic science-fiction drama film by Francis Ford Coppola."),
            Source("web", "paxos", "u", "Paxos made simple",
                   abstract="An explanation of the Paxos consensus protocol.")]
    gated = drel.relevance_gate("raft consensus algorithm for distributed systems", cand,
                                conn=conn, session_id="disc", budget=_BUDGET, min_keep=1)
    gtitles = [s.title for s in gated]
    assert "Megalopolis (film)" not in gtitles, f"FAIL: relevance gate kept the film: {gtitles}"
    assert any("Raft" in t or "Paxos" in t for t in gtitles), f"FAIL: dropped on-topic: {gtitles}"
    print(f"G-discover-live PASS (A5): relevance gate kept {gtitles} (dropped the film)")

    # ---- REPORT: real non-English discovery now returns sources (was 1 generic) ----
    zres = find_sources.find(DiscoverInput(zh, k=6), conn=conn, session_id="disc", budget=_BUDGET)
    zft = [s for s in zres.sources if s.chunks and sum(len(ch) for ch in s.chunks) > 200]
    top_t = zres.sources[0].title[:60] if zres.sources else "(none)"
    print(f"G-discover-live REPORT: non-English goal -> {len(zres.sources)} sources, "
          f"{len(zft)} with full text, top={top_t!r}")

    print("--- COST ledger (discover + digest) ---")
    for row in conn.execute("SELECT stage,tier,model,SUM(total_tokens),ROUND(SUM(usd),6),COUNT(*) "
                            "FROM cost_ledger GROUP BY stage,tier,model ORDER BY stage,tier"):
        print("  ", tuple(row))
    print("G-discover-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
