"""TDD tests for iterative DISCOVER (bounded search→observe→refine loop).

Inject fakes for adapters, rank, gate, and refine_queries — NO network.
Tests cover:
  - round-1 yields >= TARGET → refine NOT called; exactly 1 round
  - round-1 yields < TARGET, refine returns 2 queries → round 2 runs, candidates merged+deduped
  - MAX_ROUNDS cap: even if still < TARGET, no 3rd search
  - offline path: refine_queries returns [] → exactly 1 round
  - dedup: a source returned in both rounds appears once
  - cache hit → loop not entered
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

def _src(title: str, source_type: str = "arxiv", source_id: str | None = None) -> Source:
    """Build a minimal Source for testing."""
    return Source(
        source_type=source_type,
        source_id=source_id or title.lower().replace(" ", "_"),
        url=None,
        title=title,
        authority_score=0.5,
        abstract=f"Abstract for {title}",
    )


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# refine_queries tests
# ---------------------------------------------------------------------------

class TestRefineQueries:
    """Unit tests for query.refine_queries."""

    def test_offline_returns_empty(self, monkeypatch):
        """refine_queries must return [] when provider is none/offline (deterministic)."""
        monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
        conn = _db()
        result = query_mod.refine_queries(
            "open router fusion and sakana fugu orchestration",
            prior_titles=["Some paper"],
            intent="cutting-edge",
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert result == []

    def test_offline_env_value_offline_returns_empty(self, monkeypatch):
        """refine_queries must return [] when LITNAV_LLM_PROVIDER=offline."""
        monkeypatch.setenv("LITNAV_LLM_PROVIDER", "offline")
        conn = _db()
        result = query_mod.refine_queries(
            "quantum entanglement",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert result == []

    def test_live_returns_2_to_3_queries(self, monkeypatch):
        """refine_queries returns 2-3 queries when LLM provides them."""
        from litnav.llm import router
        monkeypatch.setattr(
            router, "complete_json",
            lambda *a, **k: {"queries": ["LLM model routing", "multi-agent orchestration", "LLM ensemble"]}
        )
        conn = _db()
        result = query_mod.refine_queries(
            "open router fusion and sakana fugu orchestration",
            prior_titles=["Fugu paper"],
            intent="cutting-edge",
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert isinstance(result, list)
        assert 1 <= len(result) <= 3
        assert all(isinstance(q, str) and q.strip() for q in result)

    def test_deduplicates_within_returned_queries(self, monkeypatch):
        """Duplicate queries returned by LLM should be deduplicated."""
        from litnav.llm import router
        monkeypatch.setattr(
            router, "complete_json",
            lambda *a, **k: {"queries": ["LLM routing", "LLM routing", "ensemble methods"]}
        )
        conn = _db()
        result = query_mod.refine_queries(
            "routing LLMs",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert len(result) == len(set(result))

    def test_drops_blank_queries(self, monkeypatch):
        """Blank/whitespace queries from LLM should be dropped."""
        from litnav.llm import router
        monkeypatch.setattr(
            router, "complete_json",
            lambda *a, **k: {"queries": ["valid query", "", "  ", "another valid"]}
        )
        conn = _db()
        result = query_mod.refine_queries(
            "some goal",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert all(q.strip() for q in result)

    def test_caps_at_3_queries(self, monkeypatch):
        """Even if LLM returns more than 3, we cap at 3."""
        from litnav.llm import router
        monkeypatch.setattr(
            router, "complete_json",
            lambda *a, **k: {"queries": ["q1", "q2", "q3", "q4", "q5"]}
        )
        conn = _db()
        result = query_mod.refine_queries(
            "some goal",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert len(result) <= 3

    def test_blank_llm_response_falls_back_to_empty(self, monkeypatch):
        """Blank or malformed LLM response → [] (graceful fallback)."""
        from litnav.llm import router
        monkeypatch.setattr(
            router, "complete_json",
            lambda *a, **k: {"queries": []}
        )
        conn = _db()
        result = query_mod.refine_queries(
            "some goal",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert result == []

    def test_error_in_llm_falls_back_to_empty(self, monkeypatch):
        """Exception from LLM → [] (graceful fallback, never worse than today)."""
        from litnav.llm import router
        def _raise(*a, **k):
            raise RuntimeError("network error")
        monkeypatch.setattr(router, "complete_json", _raise)
        conn = _db()
        result = query_mod.refine_queries(
            "some goal",
            prior_titles=[],
            intent=None,
            conn=conn,
            session_id="s1",
            budget=None,
        )
        assert result == []


# ---------------------------------------------------------------------------
# find() iterative loop tests
# ---------------------------------------------------------------------------

class TestFindIterativeLoop:
    """Integration tests for find_sources.find iterative loop using fakes."""

    def _make_adapter(self, sources_by_query: dict[str, list[Source]]):
        """Create a fake adapter descriptor that returns different sources per query."""
        class FakeAdapter:
            id = "fake"
            def search(self, query: str, k: int) -> list[Source]:
                return sources_by_query.get(query, [])[:k]
        return FakeAdapter()

    def test_round1_sufficient_no_refine_called(self, monkeypatch):
        """When round 1 yields >= TARGET_SOURCES, refine_queries is NOT called."""
        TARGET = find_sources.TARGET_SOURCES
        # Round-1 sources: enough to satisfy TARGET
        round1_sources = [_src(f"Paper {i}") for i in range(TARGET + 1)]

        search_calls = []
        def fake_search(q, k):
            search_calls.append(q)
            return round1_sources

        refine_calls = []
        def fake_refine(*a, **k):
            refine_calls.append(a)
            return ["should not be called"]

        conn = _db()
        monkeypatch.setattr(adapter_registry, "resolve",
                            lambda ids: [type("Ad", (), {"id": "fake", "search": lambda self, q, k: fake_search(q, k)})()
                                         for _ in range(1)])
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "normalized query")
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(rank_mod, "rank_sources", lambda goal, srcs, **k: srcs)
        monkeypatch.setattr(relevance_mod, "relevance_gate",
                            lambda goal, srcs, **k: srcs[:TARGET + 1])  # returns >= TARGET

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")

        di = DiscoverInput(goal_text="large language model routing", k=6)
        result = find_sources.find(di, conn=conn, session_id="test")

        assert refine_calls == [], "refine_queries must not be called when round-1 is sufficient"
        assert len(search_calls) == 1, f"Expected 1 search round, got {len(search_calls)}"

    def test_round1_insufficient_triggers_round2(self, monkeypatch):
        """When round 1 yields < TARGET_SOURCES, refine is called and round 2 runs."""
        TARGET = find_sources.TARGET_SOURCES
        round1_sources = [_src("Niche Paper A")]  # < TARGET
        round2_sources = [_src("Foundational Paper B"), _src("Broad Paper C")]

        search_call_count = [0]
        refine_call_count = [0]

        def fake_to_search_query(*a, **k):
            return "original query"

        def fake_refine(goal, prior_titles, intent, **k):
            refine_call_count[0] += 1
            return ["broader query 1", "broader query 2"]

        def fake_adapter_search(q, k):
            search_call_count[0] += 1
            if search_call_count[0] == 1:
                return round1_sources
            # Round 2: return new sources
            return round2_sources

        def fake_rank(goal, srcs, **k):
            return srcs

        gate_call_count = [0]
        def fake_gate(goal, srcs, **k):
            gate_call_count[0] += 1
            if gate_call_count[0] == 1:
                # Round 1: return < TARGET
                return [_src("Niche Paper A")]
            # Round 2: return >= TARGET merged
            return srcs

        conn = _db()

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                return fake_adapter_search(q, k)

        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])
        monkeypatch.setattr(query_mod, "to_search_query", fake_to_search_query)
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")

        di = DiscoverInput(goal_text="open router fusion and sakana fugu orchestration", k=6)
        result = find_sources.find(di, conn=conn, session_id="test")

        assert refine_call_count[0] == 1, "refine_queries must be called exactly once"
        assert search_call_count[0] >= 2, "Round 2 search must run"
        # Final result should be at least as many sources as round-1 alone
        assert len(result.sources) >= 1

    def test_max_rounds_cap_prevents_third_search(self, monkeypatch):
        """Even if still < TARGET, no 3rd search round is ever attempted.

        MAX_ROUNDS=2 means: round 1 (initial query) + at most 1 refine round.
        refine_queries is called at most MAX_ROUNDS-1 = 1 time total.
        """
        MAX_ROUNDS = find_sources.MAX_ROUNDS

        refine_call_count = [0]

        def fake_refine(goal, prior_titles, intent, **k):
            refine_call_count[0] += 1
            return ["query X", "query Y"]  # always returns queries

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                return [_src(f"Source for {q}")]  # always < TARGET

        def fake_gate(goal, srcs, **k):
            return []  # always 0 on-topic (worst case — never triggers stop early)

        conn = _db()
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "q1")
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(rank_mod, "rank_sources", lambda goal, srcs, **k: srcs)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")

        di = DiscoverInput(goal_text="niche niche niche topic", k=6)
        find_sources.find(di, conn=conn, session_id="test")

        # refine is called at most MAX_ROUNDS - 1 times (one refine = one extra round)
        assert refine_call_count[0] <= MAX_ROUNDS - 1, (
            f"refine called {refine_call_count[0]} times, expected <= {MAX_ROUNDS - 1}"
        )

    def test_offline_refine_returns_empty_exactly_one_round(self, monkeypatch):
        """When refine_queries returns [] (offline), exactly 1 round runs — same as single-shot behavior."""
        search_call_count = [0]

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                search_call_count[0] += 1
                return [_src("Some Paper")]  # always < TARGET

        def fake_gate(goal, srcs, **k):
            return srcs  # passthrough (no filtering)

        conn = _db()
        monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "q1")
        monkeypatch.setattr(rank_mod, "rank_sources", lambda goal, srcs, **k: srcs)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "reference")

        di = DiscoverInput(goal_text="introduction to graph neural networks", k=6)
        result = find_sources.find(di, conn=conn, session_id="test")

        assert search_call_count[0] == 1, (
            f"Offline should run exactly 1 round, got {search_call_count[0]}"
        )

    def test_dedup_source_in_both_rounds_appears_once(self, monkeypatch):
        """A source returned by both round 1 and round 2 appears only once in the final set."""
        TARGET = find_sources.TARGET_SOURCES
        duplicate_source = _src("Shared Paper", source_type="arxiv", source_id="shared_id")
        new_source = _src("New Round2 Paper", source_type="arxiv", source_id="new_id")

        round_count = [0]
        refine_called = [False]

        def fake_refine(goal, prior_titles, intent, **k):
            refine_called[0] = True
            return ["broader query"]

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                round_count[0] += 1
                if round_count[0] == 1:
                    return [duplicate_source]
                else:
                    return [duplicate_source, new_source]  # duplicate appears again

        # We need to track the actual candidates passed to rank
        ranked_candidates = []
        def fake_rank(goal, srcs, **k):
            ranked_candidates.extend(srcs)
            return srcs

        gate_call = [0]
        def fake_gate(goal, srcs, **k):
            gate_call[0] += 1
            if gate_call[0] == 1:
                return []  # round 1: < TARGET (triggers refine)
            return srcs

        conn = _db()
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "original q")
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "cutting-edge")

        di = DiscoverInput(goal_text="niche compound goal", k=6)
        result = find_sources.find(di, conn=conn, session_id="test")

        # Check that the duplicate source appears only once in the final result
        titles_in_result = [s.title for s in result.sources]
        assert titles_in_result.count("Shared Paper") <= 1, (
            "Duplicate source should appear at most once in final result"
        )

    def test_cache_hit_skips_loop(self, monkeypatch):
        """A cache hit should short-circuit the loop entirely — no adapter calls."""
        search_call_count = [0]

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                search_call_count[0] += 1
                return []

        conn = _db()
        # Pre-populate cache
        di = DiscoverInput(goal_text="cached goal text", k=6)
        cached_sources = [_src("Cached Source A"), _src("Cached Source B")]
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

        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])

        result = find_sources.find(di, conn=conn, session_id="test")

        assert result.cache_hit is True
        assert search_call_count[0] == 0, "Cache hit must not trigger any adapter search"
        assert len(result.sources) == 2

    def test_round2_survivors_included_in_final_rank(self, monkeypatch):
        """After round 2, the final rank is called on the union of r1 + r2 survivors (deduped).

        New behavior (per-sub-query judging):
        - Round-1 gate returns [] → no r1 survivors (forced refine).
        - Round-2 per-sub-query gate passes r2_source as a survivor.
        - Final rank call sees r2_source (+ shared if it passes r2 gate).
        - shared paper appears only once even if surfaced by both rounds.
        """
        r1_source = _src("Round1 Only Paper", source_type="arxiv", source_id="r1_id")
        shared = _src("Shared Paper", source_type="arxiv", source_id="shared_id")
        r2_source = _src("Round2 Only Paper", source_type="arxiv", source_id="r2_id")

        search_round = [0]

        def fake_refine(goal, prior_titles, intent, **k):
            return ["refined query"]

        class FakeAdapter:
            id = "fake"
            def search(self, q, k):
                search_round[0] += 1
                if search_round[0] == 1:
                    return [r1_source, shared]
                return [shared, r2_source]  # shared overlaps with round 1

        rank_calls = []
        def fake_rank(goal, srcs, **k):
            rank_calls.append((goal, list(srcs)))
            return srcs

        gate_call = [0]
        def fake_gate(goal, srcs, **k):
            gate_call[0] += 1
            if gate_call[0] == 1:
                return []  # round-1 gate fails → forces refine
            return srcs   # sub-query gate passes everything

        conn = _db()
        monkeypatch.setattr(adapter_registry, "resolve", lambda ids: [FakeAdapter()])
        monkeypatch.setattr(query_mod, "to_search_query", lambda *a, **k: "q")
        monkeypatch.setattr(query_mod, "refine_queries", fake_refine)
        monkeypatch.setattr(rank_mod, "rank_sources", fake_rank)
        monkeypatch.setattr(relevance_mod, "relevance_gate", fake_gate)

        from litnav.discover import intent as intent_mod
        monkeypatch.setattr(intent_mod, "classify", lambda *a, **k: "reference")

        di = DiscoverInput(goal_text="compound niche goal", k=6)
        result = find_sources.find(di, conn=conn, session_id="test")

        # The final rank call (last in rank_calls) is against goal_text and has the union.
        # r1_source did NOT pass the round-1 gate so it should NOT be in the final union.
        # r2_source passed the sub-query gate so it SHOULD be in the final result.
        assert rank_calls, "rank_sources should have been called at least once"
        final_goal, final_sources = rank_calls[-1]
        assert final_goal == "compound niche goal", "Final rank must be against goal_text"

        result_titles = {s.title for s in result.sources}
        assert "Round2 Only Paper" in result_titles, "r2_source (sub-query survivor) should be in final result"
        # shared paper is filtered out from rq_new because it was already seen in round-1 raw;
        # 'Round1 Only Paper' was NOT a survivor so it should not appear either.
        # Importantly, no source appears twice.
        assert len(result.sources) == len({s.source_id for s in result.sources}), (
            "Deduplication: each source_id should appear at most once"
        )
