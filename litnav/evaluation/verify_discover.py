"""G-discover (offline determinism/schema UNIT gate) — NOT capability evidence.

Validates deterministic logic only: adapter PARSING (canned responses), dedup, offline rank order,
intent heuristic. The CAPABILITY is proven by verify_discover_live (real APIs)."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.discover.adapters import openalex, wikipedia
from litnav.discover import rank, intent
from litnav.discover.contract import Source


def main() -> int:
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    oa = {"results": [{"id": "https://openalex.org/W1", "title": "ReAct",
          "abstract_inverted_index": {"a": [0], "b": [1]}, "cited_by_count": 1000,
          "ids": {"arxiv": "2210.03629"}, "primary_location": {"pdf_url": "u"}, "open_access": {}}]}
    s = openalex.search("q", fetch=lambda url: oa)[0]
    assert s.arxiv_id == "2210.03629" and s.abstract == "a b" and 0.0 < s.authority_score <= 1.0
    print("G-discover PASS: OpenAlex parsing")

    wsearch = {"query": {"search": [{"title": "Software agent"}]}}
    wsumm = {"title": "Software agent", "extract": "an agent", "content_urls": {"desktop": {"page": "w"}}}
    ws = wikipedia.search("q", k=1, fetch=lambda url: wsearch if "list=search" in url else wsumm)[0]
    assert ws.source_type == "wikipedia" and ws.abstract == "an agent" and ws.authority_score == 0.5
    print("G-discover PASS: Wikipedia parsing")

    a = Source("web", "a", "u", "ReAct Reasoning", 0.9)
    b = Source("web", "b", "u", "react reasoning", 0.2)
    assert len(rank.dedup([a, b])) == 1
    c = sqlite3.connect(":memory:"); init_db(c)
    out = rank.rank_sources("q", [Source("web", "l", "u", "low", 0.2),
                                  Source("web", "h", "u", "high", 0.8)], conn=c, session_id="s", k=2)
    assert [x.title for x in out] == ["high", "low"]
    print("G-discover PASS: dedup + offline rank")

    assert intent.classify("quick intro to agents", conn=c, session_id="s") == "crash-course"
    print("G-discover PASS: intent heuristic")

    # OW-3.1: query normalization + relevance gate are deterministic pass-throughs offline.
    from litnav.discover import query as dquery, relevance as drel
    assert dquery.to_search_query("给我一个关于 CRISPR 的概览", conn=c, session_id="s") == "给我一个关于 CRISPR 的概览"
    srcs = [Source("web", "a", "u", "A", 0.5), Source("web", "b", "u", "B", 0.5)]
    assert drel.relevance_gate("topic", srcs, conn=c, session_id="s") == srcs   # offline pass-through
    assert drel.relevance_gate("topic", [], conn=c, session_id="s") == []        # empty input safe
    print("G-discover PASS: query normalization + relevance gate (offline pass-through)")
    print("G-discover: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
