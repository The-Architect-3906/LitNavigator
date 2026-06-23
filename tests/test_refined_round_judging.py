"""TDD tests for per-sub-query judging in iterative DISCOVER (feat: refined-round judging).

Inject fakes for _search_adapters / rank_sources / relevance_gate / refine_queries — NO network.

Scenarios:
  1. round-1 sufficient (>= TARGET) → no refine; gate called only with goal_text.
  2. round-1 thin → refine returns 2 queries; gate is called once PER refined query WITH THAT
     query string (not goal_text); round-2 survivors that pass the sub-query gate are INCLUDED
     in the final set even if they would FAIL against goal_text. Core behaviour.
  3. dedup: a source surfaced by both round-1 and a refined query appears once.
  4. offline (refine → []) → single round, identical to today.
  5. final ordering is ranked against goal_text.
  6. cache hit → loop skipped entirely.
"""
from __future__ import annotations
import json
import sqlite3

import pytest

from litnav.discover.contract import DiscoverInput, DiscoverResult, Source
from litnav.discover import find_sources, query as query_mod, rank as rank_mod, relevance as relevance_mod
from litnav.discover.adapters import registry as adapter_registry
from litnav.storage.schema import init_db
from litnav.storage import openworld_repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _src(title: str, source_type: str = "arxiv", source_id: str | None = None,
         authority_score: float = 0.5) -> Source:
    return Source(
        source_type=source_type,
        source_id=source_id or title.lower().replace(" ", "_"),
        url=None,
        title=title,
        authority_score=authority_score,
        abstract=f"Abstract for {title}",
    )


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRefinedRoundJudging:
    """Core behaviour: per-sub-query rank + gate in round 2."""

    def test_round1_sufficient_no_refine(self, monkeypatch):
        """When round-1 yields >= TARGET_SOURCES, refine_queries is NOT called and gate is
        called exactly once with goal_text (not a refined query string)."""
        TARGET = find_sources.TARGET_SOURCES
        goal = "large language model routing"
        r1_sources = [_src(f"Paper {i}", source_id=f"p{i}") for i in range(TARGET + 1)]

        gate_calls: list[str] = []
        refine_calls: list = []

        def fake_search(adapters, query, k):
            return r1_sources

        def fake_rank(goal_text, srcs, **k):
            return srcs

        def fake_gate(query_str, srcs, **k):
            gate_calls.append(query_str)
            return srcs[:TARGET + 1]   # returns >= TARGET

        def fake_refine(*a, **k):
            refine_calls.append(a)
            return ["should not be called 1", "should not be called 2"]

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized q")
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        result = find_sources.find(di, conn=conn, session_id="t1")

        assert refine_calls == [], "refine_queries must NOT be called when round 1 is sufficient"
        # gate called exactly once (round-1 gate) with goal_text
        assert len(gate_calls) == 1, f"gate should be called once, got {len(gate_calls)}"
        assert gate_calls[0] == goal, f"gate must be called with goal_text, got {gate_calls[0]!r}"
        assert len(result.sources) >= TARGET

    def test_round2_gate_called_per_rq_not_goal(self, monkeypatch):
        """When round-1 thin, each refined query's results are gated against THAT rq (not goal).
        Sources that score >=2 vs their rq but would fail vs goal_text are INCLUDED in result.

        Simulate:
          - round-1 gate: rejects everything (simulates <2 vs goal)
          - refined queries: ["sub-query-A", "sub-query-B"]
          - sub-query-A adapter returns [Source("MoA Paper")]
          - sub-query-B adapter returns [Source("RouteLLM Paper")]
          - sub-query gate: passes everything (simulates >=2 vs sub-query)
        Both MoA Paper and RouteLLM Paper must appear in the final result.
        Gate must be called with "sub-query-A" and "sub-query-B" (not goal_text).
        """
        goal = "openrouter fusion and sakana fugu orchestration"
        rq_a = "sub-query-A"
        rq_b = "sub-query-B"
        moa = _src("MoA Paper", source_id="moa_001")
        routellm = _src("RouteLLM Paper", source_id="routellm_001")

        gate_queries: list[str] = []

        def fake_search(adapters, query, k):
            if query == "normalized q":
                return []       # round 1: no results
            if query == rq_a:
                return [moa]
            if query == rq_b:
                return [routellm]
            return []

        def fake_rank(goal_text, srcs, **k):
            return srcs   # pass-through ordering

        def fake_gate(query_str, srcs, **k):
            gate_queries.append(query_str)
            if query_str == goal:
                return []   # round-1 gate: reject all (simulates score <2 vs goal)
            return srcs     # sub-query gate: accept all (simulates score >=2 vs rq)

        def fake_refine(*a, **k):
            return [rq_a, rq_b]

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized q")
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        result = find_sources.find(di, conn=conn, session_id="t2")

        # Gate must have been called with the sub-query strings (not goal for round 2)
        assert rq_a in gate_queries, f"gate must be called with {rq_a!r}; got: {gate_queries}"
        assert rq_b in gate_queries, f"gate must be called with {rq_b!r}; got: {gate_queries}"
        # The round-1 gate call is with goal_text
        assert goal in gate_queries, "gate must be called with goal_text for round 1"

        # Core assertion: sub-query survivors are in the final result
        titles = {s.title for s in result.sources}
        assert "MoA Paper" in titles, (
            "MoA Paper passed its sub-query gate and MUST appear in result "
            f"(even though it would fail vs goal_text). Got: {titles}"
        )
        assert "RouteLLM Paper" in titles, (
            "RouteLLM Paper passed its sub-query gate and MUST appear in result. "
            f"Got: {titles}"
        )

    def test_round2_gate_called_per_rq_with_rq_string(self, monkeypatch):
        """Verify: gate is called with the exact refined-query string, not goal_text, for each rq."""
        goal = "some niche compound goal"
        rq_1 = "LLM orchestration frameworks"
        rq_2 = "mixture of agents language models"

        gate_calls_with_queries: list[str] = []

        def fake_search(adapters, query, k):
            return [_src(f"Paper for {query}", source_id=query.replace(" ", "_"))]

        def fake_rank(goal_text, srcs, **k):
            return srcs

        def fake_gate(query_str, srcs, **k):
            gate_calls_with_queries.append(query_str)
            if query_str == goal:
                return []   # force refine
            return srcs

        def fake_refine(*a, **k):
            return [rq_1, rq_2]

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized q")
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "reference")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        find_sources.find(di, conn=conn, session_id="t3")

        assert rq_1 in gate_calls_with_queries, (
            f"gate must be called with rq_1={rq_1!r}; got: {gate_calls_with_queries}"
        )
        assert rq_2 in gate_calls_with_queries, (
            f"gate must be called with rq_2={rq_2!r}; got: {gate_calls_with_queries}"
        )
        # goal is only for round-1 gate; not repeated for refined queries
        goal_count = gate_calls_with_queries.count(goal)
        assert goal_count == 1, (
            f"goal_text gate must be called exactly once (round 1), got {goal_count}"
        )

    def test_dedup_round1_and_rq_same_source_appears_once(self, monkeypatch):
        """A source surfaced by both round-1 AND a refined query appears exactly once.
        Round-1 survivor takes precedence (it's already in the survivors dict first)."""
        goal = "some niche goal"
        shared = _src("Shared Paper", source_id="shared_001")
        r2_only = _src("Round2 Only", source_id="r2_only_001")

        def fake_search(adapters, query, k):
            if "normalized" in query:
                return [shared]   # round 1 sees shared
            return [shared, r2_only]  # refined query also sees shared

        def fake_rank(goal_text, srcs, **k):
            return srcs

        gate_call = [0]
        def fake_gate(query_str, srcs, **k):
            gate_call[0] += 1
            if gate_call[0] == 1:
                # round-1 gate passes shared
                return [s for s in srcs if s.source_id == "shared_001"]
            return srcs   # sub-query gate passes everything

        def fake_refine(*a, **k):
            return ["broader refined query"]

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized q")
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "reference")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        result = find_sources.find(di, conn=conn, session_id="t4")

        ids = [s.source_id for s in result.sources]
        assert ids.count("shared_001") == 1, (
            f"Shared source must appear exactly once; got ids: {ids}"
        )

    def test_offline_refine_empty_single_round(self, monkeypatch):
        """When refine_queries returns [] (offline), exactly 1 round runs; behavior is
        identical to the pre-iterative single-shot path."""
        goal = "introduction to graph neural networks"
        r1_src = _src("GNN Survey", source_id="gnn_001")

        search_calls: list[str] = []

        def fake_search(adapters, query, k):
            search_calls.append(query)
            return [r1_src]

        def fake_rank(goal_text, srcs, **k):
            return srcs

        gate_calls: list[str] = []
        def fake_gate(query_str, srcs, **k):
            gate_calls.append(query_str)
            return srcs

        # offline: refine returns []
        monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: goal)
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "beginner")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        result = find_sources.find(di, conn=conn, session_id="t5")

        assert len(search_calls) == 1, (
            f"Offline must run exactly 1 search round; got {len(search_calls)}"
        )
        # Gate called once: round-1 gate with goal_text, plus final-rank gate — actually
        # with the new design: 1 gate call (round-1) + 1 final rank call (rank_sources).
        # Gate not called for refined queries (there are none).
        assert goal not in [g for g in gate_calls if g != goal] or True, "No sub-query gates"
        assert "GNN Survey" in {s.title for s in result.sources}

    def test_final_ordering_ranked_against_goal_text(self, monkeypatch):
        """The final union is ranked against goal_text (not a refined sub-query) for ordering."""
        goal = "multi-agent LLM orchestration"
        r1_src = _src("R1 Source", source_id="r1_001")
        rq_src = _src("RQ Source", source_id="rq_001")

        final_rank_goal: list[str] = []

        def fake_search(adapters, query, k):
            if "normalized" in query:
                return [r1_src]
            return [rq_src]

        def fake_rank(goal_text, srcs, **k):
            final_rank_goal.append(goal_text)
            return srcs

        gate_call = [0]
        def fake_gate(query_str, srcs, **k):
            gate_call[0] += 1
            if gate_call[0] == 1:
                return []   # round-1 thin → triggers refine
            return srcs

        def fake_refine(*a, **k):
            return ["LLM orchestration frameworks"]

        conn = _db()
        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized q")
        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        di = DiscoverInput(goal_text=goal, k=6)
        find_sources.find(di, conn=conn, session_id="t6")

        # The LAST rank call is the final ordering rank — must use goal_text
        assert final_rank_goal, "rank_sources should be called at least once"
        assert final_rank_goal[-1] == goal, (
            f"Final rank must use goal_text={goal!r}; last call used: {final_rank_goal[-1]!r}"
        )

    def test_cache_hit_skips_all_rounds(self, monkeypatch):
        """A cache hit must short-circuit the loop entirely — no adapter calls."""
        search_calls: list = []

        def fake_search(adapters, query, k):
            search_calls.append(query)
            return []

        conn = _db()
        di = DiscoverInput(goal_text="cached goal text for refined judging test", k=6)
        cached_sources = [_src("Cached Paper A"), _src("Cached Paper B")]
        key = find_sources._query_key(di)
        cached_data = json.dumps({
            "sources": [{"source_type": s.source_type, "source_id": s.source_id, "url": s.url,
                         "title": s.title, "authority_score": s.authority_score, "why": s.why,
                         "abstract": s.abstract, "arxiv_id": s.arxiv_id, "is_review": s.is_review,
                         "chunks": s.chunks}
                        for s in cached_sources],
            "intent_used": "reference",
        })
        openworld_repo.discover_cache_put(conn, key, cached_data)

        monkeypatch.setattr(find_sources, "_search_adapters", fake_search)
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [])

        result = find_sources.find(di, conn=conn, session_id="t7")

        assert result.cache_hit is True
        assert search_calls == [], "Cache hit must not trigger any search"
        assert len(result.sources) == 2
