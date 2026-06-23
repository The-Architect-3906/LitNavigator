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

# Fix A.2: intent-aware survey bonus, added to the rel+auth blend for is_review sources.
# Soft re-sort, never a filter — heavy for beginner/overview intents, light for cutting-edge.
_SURVEY_BONUS = {"survey": 0.20, "crash-course": 0.20, "beginner": 0.20,
                 "reference": 0.15, "cutting-edge": 0.05}
_SURVEY_BONUS_DEFAULT = 0.12


def survey_bonus(intent: str | None) -> float:
    return _SURVEY_BONUS.get((intent or "").lower(), _SURVEY_BONUS_DEFAULT)


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


def _tok(s: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if w]


def bm25_prefilter(goal_text: str, sources: list[Source], keep: int, *,
                   k1: float = 1.5, b: float = 0.75) -> list[Source]:
    """Okapi BM25 keyword prefilter over (title + abstract) vs the goal terms. Returns the top
    `keep` by BM25 score; ties keep input order. Empty query -> first `keep` in input order."""
    q = _tok(goal_text)
    if not q:
        return sources[:keep]
    docs = [_tok(f"{s.title} {s.abstract}") for s in sources]
    N = len(docs) or 1
    avgdl = (sum(len(d) for d in docs) / N) or 1.0
    # document frequency per query term
    df = {t: sum(1 for d in docs if t in d) for t in set(q)}

    def idf(t):
        n = df.get(t, 0)
        return math.log(1 + (N - n + 0.5) / (n + 0.5))

    scored = []
    for i, (s, d) in enumerate(zip(sources, docs)):
        dl = len(d) or 1
        score = 0.0
        for t in q:
            f = d.count(t)
            if f:
                score += idf(t) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scored.append((score, i, s))
    scored.sort(key=lambda x: (-x[0], x[1]))   # score desc, input order tiebreak
    return [s for _, _, s in scored[:keep]]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def rank_sources(goal_text: str, sources: list[Source], *, conn: sqlite3.Connection | None,
                 session_id: str | None, k: int = 6, budget: int | None = None,
                 intent: str | None = None) -> list[Source]:
    sources = dedup(sources)
    sources = bm25_prefilter(goal_text, sources, keep=max(k, 3 * k))  # cheap keyword prefilter
    texts = [f"{s.title}. {s.abstract}" for s in sources]
    vecs = router.embed_texts([goal_text] + texts, stage="discover", session_id=session_id,
                              conn=conn, budget=budget) if conn is not None else None
    if vecs:
        gvec, svecs = vecs[0], vecs[1:]
        bonus = survey_bonus(intent)
        scored = [(_REL_W * _cosine(gvec, sv) + _AUTH_W * s.authority_score
                   + (bonus if s.is_review else 0.0), s)
                  for s, sv in zip(sources, svecs)]
    else:
        bonus = survey_bonus(intent)
        scored = [(s.authority_score + (bonus if s.is_review else 0.0), s) for s in sources]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored[:k]]
