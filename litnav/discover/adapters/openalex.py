"""OpenAlex adapter: free, no-auth scholarly discovery with citation-based authority.
Parsing is offline-testable via an injectable `fetch`; live uses real HTTP."""
from __future__ import annotations
import json
import math
import re
import urllib.parse
import urllib.request

from litnav.discover.contract import Source

_API = "https://api.openalex.org/works"
_AUTH_SAT = math.log(5000.0)   # ~5000 citations -> authority saturates near 1.0
_ARXIV_RE = re.compile(r"\d{4}\.\d{4,5}")


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = [(i, word) for word, idxs in inv.items() for i in idxs]
    positions.sort()
    return " ".join(w for _, w in positions)


def _authority(cited: int) -> float:
    if cited <= 0:
        return 0.0
    return round(min(1.0, math.log(cited + 1) / _AUTH_SAT), 4)


def _arxiv_id_from(w: dict) -> str | None:
    raw = (w.get("ids") or {}).get("arxiv") or ""
    m = _ARXIV_RE.search(raw)
    return m.group(0) if m else None


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:
    url = f"{_API}?search={urllib.parse.quote(query)}&per_page={k}"
    data = (fetch or _http_get_json)(url)
    out: list[Source] = []
    for w in (data.get("results") or [])[:k]:
        arxiv_id = _arxiv_id_from(w)
        loc = w.get("primary_location") or {}
        oa = (w.get("open_access") or {}).get("oa_url")
        url_best = loc.get("pdf_url") or oa or loc.get("landing_page_url")
        out.append(Source(
            source_type="arxiv" if arxiv_id else "web",
            source_id=(w.get("id") or "").rstrip("/").split("/")[-1],
            url=url_best, title=w.get("title") or "(untitled)",
            authority_score=_authority(int(w.get("cited_by_count") or 0)),
            abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
            arxiv_id=arxiv_id,
        ))
    return out
