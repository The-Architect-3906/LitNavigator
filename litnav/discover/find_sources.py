"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Adapter failures are non-fatal. Every LLM/embedding
call is metered; full-text fetch is bounded to the top-k.

Iterative loop (bounded): round 1 = existing path; if on-topic yield < TARGET_SOURCES and
round < MAX_ROUNDS, refine_queries proposes broader/decomposed queries. Each refined query is
ranked and gated against THAT sub-query (not the original goal), so decomposition pays off.
Offline (refine_queries returns []) → single-round, unchanged behaviour.

Round-1: search with sq, rank against goal_text, gate against goal_text (strict precision).
Round-2 (refined): for EACH refined query rq:
  - search adapters with rq
  - rank results against rq (top di.k)
  - gate that group against rq (a paper is kept if on-topic for the sub-query it answers)
Final set = round-1 survivors ∪ all refined-query survivors, deduped by (source_type, source_id).
  Round-1 survivors take precedence on dup. Final ordering is rank against goal_text (ordering only;
  no re-gating — that would undo the point of per-sub-query gating).
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import sqlite3

from litnav.discover.contract import DiscoverInput, DiscoverResult, Source
from litnav.discover import intent as intent_mod, rank as rank_mod, fulltext as fulltext_mod
from litnav.discover import relevance as relevance_mod
from litnav.discover import query as query_mod
from litnav.discover.adapters import registry as adapter_registry
from litnav.storage import openworld_repo

_FULLTEXT_TOPK = 3
_WIKIPEDIA_K = 3   # Wikipedia always fetches a smaller set

TARGET_SOURCES = 2   # minimum on-topic sources to stop the loop early
MAX_ROUNDS = 2       # hard cap: round 1 + at most one refine round


def _query_key(di: DiscoverInput) -> str:
    adapter_key = ",".join(sorted(di.selected_adapters)) if di.selected_adapters else ""
    raw = f"{di.goal_text}|{di.k}|{adapter_key}"
    return "discover:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _search_adapters(adapters, query: str, k: int) -> list[Source]:
    """Search all adapters with query, return combined candidates. Non-fatal on failure."""
    sources = []
    for ad in adapters:
        n = _WIKIPEDIA_K if ad.id == "wikipedia" else k * 2
        try:
            sources.extend(ad.search(query, k=n))
        except Exception:
            pass
    return sources


def find(di: DiscoverInput, *, conn: sqlite3.Connection, session_id: str | None = None,
         budget: int | None = None) -> DiscoverResult:
    # Cache short-circuit (unchanged — the loop is internal; key stays goal-derived)
    key = _query_key(di)
    cached = openworld_repo.discover_cache_get(conn, key)
    if cached is not None:
        data = json.loads(cached)
        sources = [Source(**s) for s in data["sources"]]
        return DiscoverResult(sources=sources, intent_used=data["intent_used"], cache_hit=True)

    # Round 1 setup (unchanged)
    sq = query_mod.to_search_query(di.goal_text, conn=conn, session_id=session_id, budget=budget)
    intent = intent_mod.classify(di.goal_text, conn=conn, session_id=session_id,
                                 explicit=di.intent, budget=budget)
    adapters = adapter_registry.resolve(di.selected_adapters)

    # -----------------------------------------------------------------------
    # Round 1: search with sq, rank against goal_text, gate against goal_text
    # -----------------------------------------------------------------------
    r1_raw = _search_adapters(adapters, sq, di.k)
    r1_ranked = rank_mod.rank_sources(di.goal_text, r1_raw, conn=conn, session_id=session_id,
                                      k=di.k, budget=budget, intent=intent)
    r1_survivors = relevance_mod.relevance_gate(
        di.goal_text, r1_ranked, conn=conn, session_id=session_id,
        budget=budget, min_keep=min(2, len(r1_ranked))
    )

    # Build the survivors set keyed by (source_type, source_id).
    # Round-1 survivors are inserted first; they take precedence on dup.
    survivors: dict[tuple[str, str], Source] = {
        (s.source_type, s.source_id): s for s in r1_survivors
    }

    # Stop early if round 1 already has enough on-topic sources (common case unchanged).
    if len(survivors) < TARGET_SOURCES and MAX_ROUNDS >= 2:
        # -----------------------------------------------------------------------
        # Round 2 (refined): per refined query, rank + gate against THAT sub-query
        # -----------------------------------------------------------------------
        refined = query_mod.refine_queries(
            di.goal_text,
            prior_titles=[s.title for s in r1_survivors[:5]],
            intent=intent,
            conn=conn,
            session_id=session_id,
            budget=budget,
        )
        if refined:
            # Track sources already seen across rounds (by (source_type, source_id)) so
            # we don't re-add a source that round 1 already committed.  We still search
            # broadly but only insert truly new sources into the survivors dict.
            seen_ids: set[tuple[str, str]] = set(survivors.keys())
            # Also track raw round-1 candidates so we can detect dups from adapters.
            r1_ids: set[tuple[str, str]] = {(s.source_type, s.source_id) for s in r1_raw}

            for rq in refined:
                rq_raw = _search_adapters(adapters, rq, di.k)
                # Deduplicate within this sub-query's results (drop already-committed sources;
                # they keep their round-1 slot).
                rq_new = [s for s in rq_raw if (s.source_type, s.source_id) not in seen_ids]
                if not rq_new:
                    continue

                # Rank THIS sub-query's candidates against the sub-query, not the goal.
                rq_ranked = rank_mod.rank_sources(rq, rq_new, conn=conn, session_id=session_id,
                                                  k=di.k, budget=budget, intent=intent)
                # Gate THIS sub-query's ranked candidates against the sub-query.
                rq_survivors = relevance_mod.relevance_gate(
                    rq, rq_ranked, conn=conn, session_id=session_id,
                    budget=budget, min_keep=min(2, len(rq_ranked))
                )
                for s in rq_survivors:
                    ck = (s.source_type, s.source_id)
                    if ck not in survivors:
                        survivors[ck] = s
                        seen_ids.add(ck)

    # -----------------------------------------------------------------------
    # Final ordering: rank the union against goal_text (ordering only — no re-gate).
    # -----------------------------------------------------------------------
    union = list(survivors.values())
    ranked = rank_mod.rank_sources(di.goal_text, union, conn=conn, session_id=session_id,
                                   k=di.k, budget=budget, intent=intent)

    # attach_fulltext runs ONCE after the loop on the final ranked set (unchanged)
    fulltext_mod.attach_fulltext(ranked, top_k=min(_FULLTEXT_TOPK, len(ranked)))
    for s in ranked:
        if not s.why:
            s.why = f"intent={intent}; authority={s.authority_score}"

    result_json = json.dumps({
        "sources": [dataclasses.asdict(s) for s in ranked],
        "intent_used": intent,
    })
    openworld_repo.discover_cache_put(conn, key, result_json)
    return DiscoverResult(sources=ranked, intent_used=intent, cache_hit=False)
