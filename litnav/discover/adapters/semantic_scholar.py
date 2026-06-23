"""Semantic Scholar adapter: ML-ranked scholarly search with TLDRs.
Injectable `fetch` for offline testing; live uses real HTTP.
Rate limit: ~1 RPS shared (no key). Non-fatal on 429/outage — caller wraps in try/except."""
from __future__ import annotations
import json
import math
import urllib.parse
import urllib.request

from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review

_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,abstract,tldr,citationCount,externalIds,openAccessPdf,year,publicationTypes"
_AUTH_SAT = math.log(5000.0)   # same saturation as openalex._authority


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _authority(cited: int) -> float:
    if cited <= 0:
        return 0.0
    return round(min(1.0, math.log(cited + 1) / _AUTH_SAT), 4)


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:
    url = (f"{_API}?query={urllib.parse.quote(query)}"
           f"&fields={_FIELDS}&limit={k}")
    data = (fetch or _http_get_json)(url)
    out: list[Source] = []
    for p in (data.get("data") or [])[:k]:
        paper_id = p.get("paperId") or ""
        arxiv_id = (p.get("externalIds") or {}).get("ArXiv")
        oa_pdf = (p.get("openAccessPdf") or {}).get("url")
        url_best = oa_pdf or f"https://www.semanticscholar.org/paper/{paper_id}"
        abstract = p.get("abstract") or ""
        if not abstract:
            tldr = p.get("tldr") or {}
            abstract = tldr.get("text") or ""
        out.append(Source(
            source_type="arxiv" if arxiv_id else "web",
            source_id=paper_id,
            url=url_best,
            title=p.get("title") or "(untitled)",
            authority_score=_authority(int(p.get("citationCount") or 0)),
            abstract=abstract,
            arxiv_id=arxiv_id,
            is_review=("Review" in (p.get("publicationTypes") or [])) or looks_like_review(p.get("title") or ""),
        ))
    return out
