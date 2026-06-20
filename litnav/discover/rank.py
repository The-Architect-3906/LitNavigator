"""Rank + dedup discovered sources. Relevance = embedding cosine of (title+abstract) vs the goal
(metered) when available; offline falls back to authority order. Final score blends relevance and
authority. SPECTER rerank is a future RECORDED_NEEDS item."""
from __future__ import annotations
import math
import re
import sqlite3

from litnav.discover.contract import Source
from litnav.llm import router

_REL_W, _AUTH_W = 0.7, 0.3


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def dedup(sources: list[Source]) -> list[Source]:
    """Drop near-duplicate titles; keep the higher-authority copy."""
    best: dict[str, Source] = {}
    for s in sources:
        key = _norm_title(s.title)
        if key not in best or s.authority_score > best[key].authority_score:
            best[key] = s
    return list(best.values())


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def rank_sources(goal_text: str, sources: list[Source], *, conn: sqlite3.Connection | None,
                 session_id: str | None, k: int = 6, budget: int | None = None) -> list[Source]:
    sources = dedup(sources)
    texts = [f"{s.title}. {s.abstract}" for s in sources]
    vecs = router.embed_texts([goal_text] + texts, stage="discover", session_id=session_id,
                              conn=conn, budget=budget) if conn is not None else None
    if vecs:
        gvec, svecs = vecs[0], vecs[1:]
        scored = [(_REL_W * _cosine(gvec, sv) + _AUTH_W * s.authority_score, s)
                  for s, sv in zip(sources, svecs)]
    else:
        scored = [(s.authority_score, s) for s in sources]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored[:k]]
