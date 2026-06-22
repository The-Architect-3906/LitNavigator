"""Wikipedia adapter: clean encyclopedic background. Injectable fetch for offline tests."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review

_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit={k}&srsearch={q}"
_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_WIKI_AUTHORITY = 0.5


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search(query: str, k: int = 5, *, fetch=None) -> list[Source]:
    get = fetch or _http_get_json
    sres = get(_SEARCH.format(k=k, q=urllib.parse.quote(query)))
    hits = ((sres.get("query") or {}).get("search") or [])[:k]
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
