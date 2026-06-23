"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Adapter failures are non-fatal. Every LLM/embedding
call is metered; full-text fetch is bounded to the top-k.

Iterative loop (bounded): round 1 = existing path; if on-topic yield < TARGET_SOURCES and
round < MAX_ROUNDS, refine_queries proposes broader/decomposed queries, merges candidates, and
re-ranks. Offline (refine_queries returns []) → single-round, unchanged behaviour.
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

    # Candidates dict keyed by (source_type, source_id) for cross-round dedup
    candidates: dict[tuple[str, str], Source] = {}

    on_topic: list[Source] = []

    for round_num in range(1, MAX_ROUNDS + 1):
        if round_num == 1:
            # Round 1: use the normalized search query
            new_sources = _search_adapters(adapters, sq, di.k)
        else:
            # Round 2+: use refined queries (one adapter sweep per refined query)
            # refine_queries decides to return [] offline → we never reach here offline
            refined = query_mod.refine_queries(
                di.goal_text,
                prior_titles=[s.title for s in on_topic[:5]],
                intent=intent,
                conn=conn,
                session_id=session_id,
                budget=budget,
            )
            if not refined:
                break  # offline or LLM gave no ideas → stop
            new_sources = []
            for rq in refined:
                new_sources.extend(_search_adapters(adapters, rq, di.k))

        # Accumulate candidates (dedup by (source_type, source_id))
        for s in new_sources:
            ck = (s.source_type, s.source_id)
            if ck not in candidates:
                candidates[ck] = s

        # Re-rank and gate the MERGED candidate set each round
        merged = list(candidates.values())
        ranked = rank_mod.rank_sources(di.goal_text, merged, conn=conn, session_id=session_id,
                                       k=di.k, budget=budget, intent=intent)
        on_topic = relevance_mod.relevance_gate(
            di.goal_text, ranked, conn=conn, session_id=session_id,
            budget=budget, min_keep=min(2, len(ranked))
        )

        # Observe: stop early if we have enough on-topic sources
        if len(on_topic) >= TARGET_SOURCES:
            break

        # If this is the last allowed round, don't refine again — just stop
        if round_num >= MAX_ROUNDS:
            break

        # Otherwise: loop will refine on next iteration

    # ranked = the last on_topic set from the loop (best available)
    ranked = on_topic

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
