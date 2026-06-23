"""Stack Exchange adapter: Q&A search via Stack Exchange API v2.3.
Injectable `fetch` for offline testing; live uses real HTTP.
Rate limit: 300 req/day (no key). Non-fatal on 429/outage — caller wraps in try/except."""
from __future__ import annotations
import json
import math
import re
import urllib.parse
import urllib.request

from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review

_API = "https://api.stackexchange.com/2.3/search/advanced"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_AUTH_SAT = math.log(1000.0)   # saturation at 1000 score


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub("", text)).strip()


def _authority(score: int) -> float:
    if score <= 0:
        return 0.0
    return round(min(1.0, math.log(score + 1) / _AUTH_SAT), 4)


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:
    url = (
        f"{_API}?order=desc&sort=relevance"
        f"&q={urllib.parse.quote(query)}"
        f"&site=stackoverflow&filter=withbody&pagesize={k}"
    )
    try:
        data = (fetch or _http_get_json)(url)
    except Exception:
        return []
    out: list[Source] = []
    for item in (data.get("items") or [])[:k]:
        body_raw = item.get("body") or ""
        abstract = _strip_html(body_raw)[:400]
        score = int(item.get("score") or 0)
        out.append(Source(
            source_type="stackoverflow",
            source_id=str(item.get("question_id") or ""),
            url=item.get("link"),
            title=item.get("title") or "(untitled)",
            authority_score=_authority(score),
            abstract=abstract,
            arxiv_id=None,
            is_review=looks_like_review(item.get("title") or ""),
        ))
    return out
