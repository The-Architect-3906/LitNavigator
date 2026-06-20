"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Adapter failures are non-fatal. Every LLM/embedding
call is metered; full-text fetch is bounded to the top-k."""
from __future__ import annotations
import sqlite3

from litnav.discover.contract import DiscoverInput, DiscoverResult
from litnav.discover import intent as intent_mod, rank as rank_mod, fulltext as fulltext_mod
from litnav.discover.adapters import openalex, wikipedia

_FULLTEXT_TOPK = 3


def find(di: DiscoverInput, *, conn: sqlite3.Connection, session_id: str | None = None,
         budget: int | None = None) -> DiscoverResult:
    intent = intent_mod.classify(di.goal_text, conn=conn, session_id=session_id,
                                 explicit=di.intent, budget=budget)
    sources = []
    for adapter, n in ((openalex, di.k * 2), (wikipedia, 3)):
        try:
            sources.extend(adapter.search(di.goal_text, k=n))
        except Exception:
            pass                                   # an adapter outage is non-fatal
    ranked = rank_mod.rank_sources(di.goal_text, sources, conn=conn, session_id=session_id,
                                   k=di.k, budget=budget)
    fulltext_mod.attach_fulltext(ranked, top_k=min(_FULLTEXT_TOPK, len(ranked)))
    for s in ranked:
        if not s.why:
            s.why = f"intent={intent}; authority={s.authority_score}"
    return DiscoverResult(sources=ranked, intent_used=intent)
