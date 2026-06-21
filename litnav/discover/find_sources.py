"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Adapter failures are non-fatal. Every LLM/embedding
call is metered; full-text fetch is bounded to the top-k."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import sqlite3

from litnav.discover.contract import DiscoverInput, DiscoverResult, Source
from litnav.discover import intent as intent_mod, rank as rank_mod, fulltext as fulltext_mod
from litnav.discover import relevance as relevance_mod
from litnav.discover import query as query_mod
from litnav.discover.adapters import openalex, wikipedia
from litnav.storage import openworld_repo

_FULLTEXT_TOPK = 3


def _query_key(di: DiscoverInput) -> str:
    raw = f"{di.goal_text}|{di.k}"
    return "discover:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def find(di: DiscoverInput, *, conn: sqlite3.Connection, session_id: str | None = None,
         budget: int | None = None) -> DiscoverResult:
    key = _query_key(di)
    cached = openworld_repo.discover_cache_get(conn, key)
    if cached is not None:
        data = json.loads(cached)
        sources = [Source(**s) for s in data["sources"]]
        return DiscoverResult(sources=sources, intent_used=data["intent_used"], cache_hit=True)

    sq = query_mod.to_search_query(di.goal_text, conn=conn, session_id=session_id, budget=budget)
    intent = intent_mod.classify(di.goal_text, conn=conn, session_id=session_id,
                                 explicit=di.intent, budget=budget)
    sources = []
    for adapter, n in ((openalex, di.k * 2), (wikipedia, 3)):
        try:
            sources.extend(adapter.search(sq, k=n))
        except Exception:
            pass                                   # an adapter outage is non-fatal
    ranked = rank_mod.rank_sources(sq, sources, conn=conn, session_id=session_id,
                                   k=di.k, budget=budget)
    ranked = relevance_mod.relevance_gate(sq, ranked, conn=conn, session_id=session_id,
                                          budget=budget, min_keep=min(2, len(ranked)))
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
