"""arXiv direct-search adapter: preprint relevance search via Atom XML API.
Injectable `fetch` returns bytes; live uses real HTTP.
Rate limit: 1 req/3 sec. Non-fatal on outage — caller wraps in try/except."""
from __future__ import annotations
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from litnav.discover.contract import Source

_API = "http://export.arxiv.org/api/query"
_NS = "http://www.w3.org/2005/Atom"
_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")
_AUTHORITY = 0.35   # fixed; no citation data in arXiv API


def _http_get_bytes(url: str) -> bytes:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _extract_arxiv_id(entry_id: str) -> str | None:
    m = _ARXIV_ID_RE.search(entry_id)
    return m.group(1) if m else None


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:
    url = (f"{_API}?search_query=all:{urllib.parse.quote(query)}"
           f"&start=0&max_results={k}&sortBy=relevance")
    raw = (fetch or _http_get_bytes)(url)
    root = ET.fromstring(raw)
    out: list[Source] = []
    for entry in list(root.iter(f"{{{_NS}}}entry"))[:k]:
        entry_id = (entry.findtext(f"{{{_NS}}}id") or "").strip()
        arxiv_id = _extract_arxiv_id(entry_id)
        title = (entry.findtext(f"{{{_NS}}}title") or "").strip()
        abstract = (entry.findtext(f"{{{_NS}}}summary") or "").strip()
        # Prefer PDF link, fall back to alternate (abstract page)
        url_best: str | None = None
        for link in entry.findall(f"{{{_NS}}}link"):
            rel = link.get("rel", "")
            ltype = link.get("type", "")
            href = link.get("href", "")
            if rel == "related" and "pdf" in ltype:
                url_best = href
                break
            if rel == "alternate" and url_best is None:
                url_best = href
        out.append(Source(
            source_type="arxiv",
            source_id=arxiv_id or entry_id,
            url=url_best,
            title=title or "(untitled)",
            authority_score=_AUTHORITY,
            abstract=abstract,
            arxiv_id=arxiv_id,
        ))
    return out
