"""Wikipedia adapter: clean encyclopedic background. Injectable fetch for offline tests."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review

_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit={k}&srsearch={q}"
_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_EXTRACTS = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
             "&format=json&redirects=1&titles={title}")
_WIKI_AUTHORITY = 0.5


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


import re as _re
_STOP = frozenset(
    "the a an and or of to in on at for with from by is are how do does what why when "
    "across over into things step steps thing introduction intro basics overview understand "
    "learn explain about across-steps".split())
_JUNK = _re.compile(r"\([^)]*\b(film|tv series|album|song|novel|band|video game|disambiguation)\b[^)]*\)"
                    r"|^list of ", _re.IGNORECASE)   # catches "(1935 film)", "(TV series)", etc.


def _terms(text: str) -> set[str]:
    return {w for w in _re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def _score_hit(q_terms: set[str], title: str, snippet: str) -> float:
    """Topical match of a Wikipedia candidate to the query: title overlap (heavy) + snippet overlap;
    disambiguation/film/list junk is pushed below anything on-topic."""
    if _JUNK.search(title or ""):
        return -1.0
    snip = _re.sub(r"<[^>]+>", " ", snippet or "")
    return 2.0 * len(q_terms & _terms(title)) + 1.0 * min(3, len(q_terms & _terms(snip)))


def search(query: str, k: int = 5, *, fetch=None) -> list[Source]:
    get = fetch or _http_get_json
    pool = max(k * 4, 8)                          # fetch a bigger candidate pool to choose from
    sres = get(_SEARCH.format(k=pool, q=urllib.parse.quote(query)))
    cands = ((sres.get("query") or {}).get("search") or [])
    # Re-rank by topical match to the query (drop junk); Wikipedia's own keyword order floats
    # tail-word matches like "The 39 Steps (film)" for "agent memory across steps".
    q_terms = _terms(query)
    if q_terms:
        # Stable sort by topical score (junk scores -1 → sinks below any real candidate); keep top-k.
        # We don't hard-drop score-0 items — a relevant title with no lexical overlap (e.g. plural
        # mismatch) still beats junk and the downstream LLM relevance_gate makes the final call.
        hits = sorted(cands, key=lambda h: _score_hit(q_terms, h.get("title") or "",
                                                      h.get("snippet") or ""), reverse=True)[:k]
    else:
        hits = cands[:k]
    out: list[Source] = []
    for h in hits:
        title = h.get("title") or ""
        summ = get(_SUMMARY.format(title=urllib.parse.quote(title.replace(" ", "_"))))
        url = (((summ.get("content_urls") or {}).get("desktop") or {}).get("page"))
        out.append(Source(
            source_type="wikipedia", source_id=title.replace(" ", "_"), url=url,
            title=summ.get("title") or title, authority_score=_WIKI_AUTHORITY,
            abstract=summ.get("extract") or "",
            is_review=looks_like_review(summ.get("title") or title),
        ))
    return out


def fetch_article(title: str, *, fetch=None) -> str:
    """Full plain-text article via MediaWiki extracts (UA header reused). '' on any failure.

    Fix A.3: the summary endpoint returns only the lead sentence (~100 chars); the full article
    (tens of KB) is the general-concepts backbone for beginner/survey goals.
    """
    get = fetch or _http_get_json
    try:
        data = get(_EXTRACTS.format(title=urllib.parse.quote(title.replace(" ", "_"))))
        pages = (data.get("query") or {}).get("pages") or {}
        for pg in pages.values():
            if pg.get("extract"):
                return pg["extract"]
    except Exception:
        pass
    return ""
