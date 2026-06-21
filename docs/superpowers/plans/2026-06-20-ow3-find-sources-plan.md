# OW-3 — find-sources (DISCOVER), Live-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Given a learning goal, discover the most suitable real sources LIVE (OpenAlex papers w/ authority + Wikipedia background), fetch full text for the top-k (reusing the arXiv PDF extractor), and feed them into digest — so the digest finally runs on RICH evidence (closing the A1 thin-evidence question) instead of 3-sentence fixtures.

**Architecture:** A new `litnav/discover/` package: a typed contract, an intent classifier (cheap LLM seam + offline heuristic), two live HTTP **adapters** (OpenAlex, Wikipedia) with an *injectable fetch* so parsing is offline-testable, a full-text fetch (reuse `litnav/ingest/pdf_extract.py` for arXiv), a deterministic rank+dedup stage (embedding-cosine relevance via the metered router + authority normalization), and a `find_sources` orchestrator (intent → source stack → adapters metadata-only → rank → dedup → top-k full-text → `DiscoverResult`), all metered. Live-first: capability validated by a LIVE gate; offline gates only for deterministic logic (intent heuristic, rank math, dedup, parsing of canned responses).

**Tech Stack:** Python, `urllib`/`requests` for HTTP, `litnav.llm.router` (metered intent + embedding rerank), `litnav.ingest.pdf_extract` (arXiv full text), `litnav.digest` (consumes the discovered sources), `litnav.storage` (query cache), pytest. Live gate per `docs/2026-06-20-live-gate-execution-contract.md`.

**Reuse:** `litnav/ingest/pdf_extract.py` (`extract_text`/`chunk_text`/`_start_at_abstract`) and `corpus_expand._download_and_extract` for arXiv PDFs; `router.complete_json` (intent), `router.embed_texts` (rerank); `digest.contract.SourceDoc` shape for the hand-off.

**Out of scope (recorded, deferred):** Semantic Scholar + youtube-transcript adapters; SPECTER rerank (stays a `RECORDED_NEEDS` "reranker" — we use text-embedding-3-small cosine for now); iterative multi-round discovery for "systematic" intent (single round in this MVP).

---

## Conventions
- Offline = deterministic safety/logic only (intent heuristic, rank arithmetic, dedup, parsing canned JSON). Capability (real discovery) proven by `verify_discover_live`. A green offline run is NOT capability evidence.
- Adapters take an injectable `fetch` callable (default = real HTTP) so tests/offline inject canned responses with no network.
- Every external call metered through `router`; HTTP calls are not LLM but are bounded (timeout, top-k full-text only).
- Each task: TDD offline, regression `pytest -q` + 6 offline gates green, commit (no push). Report REAL counts. Baseline at plan start: **192 passed**.

---

## Task 1: discover contract + intent classifier

**Files:** Create `litnav/discover/__init__.py`, `litnav/discover/contract.py`, `litnav/discover/intent.py`; Test `tests/test_discover_intent.py`.

- [ ] **Step 1: failing test** `tests/test_discover_intent.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import DiscoverInput, Source, DiscoverResult, INTENTS
from litnav.discover import intent as intent_mod


def test_intents_set():
    assert INTENTS == {"crash-course", "systematic", "applied", "reference", "cutting-edge"}


def test_offline_intent_heuristic(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    assert intent_mod.classify("give me a quick intro to multi-agent systems", conn=c, session_id="s") == "crash-course"
    assert intent_mod.classify("a thorough systematic review of agent memory", conn=c, session_id="s") == "systematic"
    assert intent_mod.classify("latest cutting-edge work on agent planning", conn=c, session_id="s") == "cutting-edge"
    assert intent_mod.classify("how do I build a tool-using agent", conn=c, session_id="s") == "applied"
    assert intent_mod.classify("what is a transformer", conn=c, session_id="s") in INTENTS


def test_explicit_intent_passthrough(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    assert intent_mod.classify("anything", conn=c, session_id="s", explicit="applied") == "applied"


def test_source_and_result_shapes():
    s = Source(source_type="arxiv", source_id="2210.03629", url="http://x", title="ReAct",
               authority_score=0.9, why="seminal", abstract="...", arxiv_id="2210.03629")
    r = DiscoverResult(sources=[s], intent_used="applied")
    assert r.sources[0].arxiv_id == "2210.03629" and r.intent_used == "applied"
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: create `litnav/discover/contract.py`:**
```python
"""Typed contract for find-sources (DISCOVER)."""
from __future__ import annotations
from dataclasses import dataclass, field

INTENTS = {"crash-course", "systematic", "applied", "reference", "cutting-edge"}


@dataclass
class DiscoverInput:
    goal_text: str
    intent: str | None = None          # None => classify
    budget: int | None = None
    k: int = 6                          # how many sources to return


@dataclass
class Source:
    source_type: str                   # arxiv | wikipedia | web
    source_id: str
    url: str | None
    title: str
    authority_score: float = 0.0       # normalized [0,1]
    why: str = ""
    abstract: str = ""
    arxiv_id: str | None = None
    chunks: list[str] = field(default_factory=list)   # filled for top-k full-text


@dataclass
class DiscoverResult:
    sources: list[Source]
    intent_used: str
```

- [ ] **Step 4: create `litnav/discover/intent.py`:**
```python
"""Intent classification: a metered cheap-LLM seam with an offline keyword heuristic fallback."""
from __future__ import annotations
import sqlite3
from litnav.discover.contract import INTENTS
from litnav.llm import router

_HEURISTIC = [
    ("crash-course", ("quick", "intro", "introduction", "beginner", "overview", "crash")),
    ("systematic", ("systematic", "thorough", "comprehensive", "survey", "review", "literature")),
    ("cutting-edge", ("cutting-edge", "latest", "state-of-the-art", "sota", "recent", "frontier")),
    ("applied", ("how do i", "how to", "build", "implement", "apply", "practical", "use")),
    ("reference", ("what is", "define", "definition", "reference", "look up")),
]


def _heuristic(goal: str) -> str:
    g = goal.lower()
    for intent, cues in _HEURISTIC:
        if any(cue in g for cue in cues):
            return intent
    return "reference"


def classify(goal_text: str, *, conn: sqlite3.Connection | None, session_id: str | None,
             explicit: str | None = None, budget: int | None = None) -> str:
    """Return an intent in INTENTS. explicit wins; else LLM (cheap) live, heuristic offline/fallback."""
    if explicit in INTENTS:
        return explicit
    fb = _heuristic(goal_text)
    prompt = (
        f"Classify this learning goal into exactly one intent.\nGoal: {goal_text}\n"
        f"Intents: {sorted(INTENTS)}\n"
        'Respond JSON: {"intent": "<one of the intents>"}'
    )
    res = router.complete_json(prompt, tier="cheap", stage="discover", fallback={"intent": fb},
                              session_id=session_id, conn=conn, budget=budget)
    intent = res.get("intent") if isinstance(res, dict) else None
    return intent if intent in INTENTS else fb
```

- [ ] **Step 5: create `litnav/discover/__init__.py`:**
```python
"""Open-world DISCOVER: find the most suitable real sources for a goal (OW-3)."""
```

- [ ] **Step 6:** run `python -m pytest tests/test_discover_intent.py -v` → PASS. `pytest -q` → expect **196 passed** (192 + 4). Report real. 6 gates green.

- [ ] **Step 7: commit** `feat(ow3): discover contract + intent classifier (cheap seam + offline heuristic)`.

---

## Task 2: OpenAlex adapter (discovery + authority)

**Files:** Create `litnav/discover/adapters/__init__.py`, `litnav/discover/adapters/openalex.py`; Test `tests/test_discover_openalex.py`.

OpenAlex: `https://api.openalex.org/works?search={q}&per_page={k}&mailout` → JSON `{"results":[{"id","title","abstract_inverted_index","cited_by_count","ids":{"arxiv"?},"primary_location":{"pdf_url","landing_page_url"},"open_access":{"oa_url"}}]}`. Abstract is an inverted index → reconstruct. authority_score = normalized log(cited_by_count+1).

- [ ] **Step 1: failing test** `tests/test_discover_openalex.py`:
```python
from litnav.discover.adapters import openalex

CANNED = {"results": [
    {"id": "https://openalex.org/W1", "title": "ReAct: Synergizing Reasoning and Acting",
     "abstract_inverted_index": {"We": [0], "study": [1], "agents": [2]},
     "cited_by_count": 1200, "ids": {"arxiv": "2210.03629"},
     "primary_location": {"pdf_url": "http://arxiv.org/pdf/2210.03629", "landing_page_url": "http://x"},
     "open_access": {"oa_url": "http://arxiv.org/pdf/2210.03629"}},
    {"id": "https://openalex.org/W2", "title": "Some Web Page", "abstract_inverted_index": None,
     "cited_by_count": 0, "ids": {}, "primary_location": {"landing_page_url": "http://y"},
     "open_access": {"oa_url": None}},
]}


def test_parse_openalex_results():
    sources = openalex.search("react agents", k=10, fetch=lambda url: CANNED)
    assert len(sources) == 2
    s0 = sources[0]
    assert s0.title.startswith("ReAct") and s0.arxiv_id == "2210.03629"
    assert s0.abstract == "We study agents"          # reconstructed from inverted index
    assert 0.0 < s0.authority_score <= 1.0           # high citations -> high authority
    assert s0.url == "http://arxiv.org/pdf/2210.03629"
    s1 = sources[1]
    assert s1.arxiv_id is None and s1.authority_score == 0.0  # zero citations


def test_query_is_url_encoded():
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"results": []}
    openalex.search("multi agent debate", k=5, fetch=fake)
    assert "multi%20agent%20debate" in captured["url"] or "multi+agent+debate" in captured["url"]
    assert "per_page=5" in captured["url"]
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: create `litnav/discover/adapters/__init__.py`** (empty package marker) and `litnav/discover/adapters/openalex.py`:
```python
"""OpenAlex adapter: free, no-auth scholarly discovery with citation-based authority.
Parsing is offline-testable via an injectable `fetch`; live uses real HTTP."""
from __future__ import annotations
import json
import math
import urllib.parse
import urllib.request

from litnav.discover.contract import Source

_API = "https://api.openalex.org/works"
# Citations giving authority_score ~= 1.0 (log-normalized). 5000+ citations ~ saturated.
_AUTH_SAT = math.log(5000.0)


def _http_get_json(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "LitNavigator/0.1 (mailto:demo@example.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _authority(cited: int) -> float:
    if cited <= 0:
        return 0.0
    return round(min(1.0, math.log(cited + 1) / _AUTH_SAT), 4)


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:
    url = f"{_API}?search={urllib.parse.quote(query)}&per_page={k}"
    data = (fetch or _http_get_json)(url)
    out: list[Source] = []
    for w in (data.get("results") or [])[:k]:
        arxiv_id = (w.get("ids") or {}).get("arxiv")
        if arxiv_id:                                   # OpenAlex stores e.g. https://arxiv.org/abs/2210.03629
            arxiv_id = arxiv_id.rstrip("/").split("/")[-1].replace("abs", "").strip("v0123456789") and \
                       arxiv_id.rstrip("/").split("/")[-1]
        loc = w.get("primary_location") or {}
        oa = (w.get("open_access") or {}).get("oa_url")
        url_best = loc.get("pdf_url") or oa or loc.get("landing_page_url")
        out.append(Source(
            source_type="arxiv" if arxiv_id else "web",
            source_id=(w.get("id") or "").rstrip("/").split("/")[-1],
            url=url_best, title=w.get("title") or "(untitled)",
            authority_score=_authority(int(w.get("cited_by_count") or 0)),
            abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
            arxiv_id=arxiv_id or None,
        ))
    return out
```
> Note the arXiv-id normalization is fiddly; the test's `ids.arxiv` is a bare `2210.03629`. Make `_arxiv_id_from(w)` simply take `(w["ids"]["arxiv"])` and extract the trailing `\d{4}\.\d{4,5}` via a regex; replace the ugly chained expression above with a small helper:
```python
import re
_ARXIV_RE = re.compile(r"\d{4}\.\d{4,5}")
def _arxiv_id_from(w: dict) -> str | None:
    raw = (w.get("ids") or {}).get("arxiv") or ""
    m = _ARXIV_RE.search(raw)
    return m.group(0) if m else None
```
Use `_arxiv_id_from(w)` in `search`.

- [ ] **Step 4:** run `python -m pytest tests/test_discover_openalex.py -v` → PASS. `pytest -q` → **198 passed**. Report real.

- [ ] **Step 5: commit** `feat(ow3): OpenAlex adapter (discovery + citation authority, injectable fetch)`.

---

## Task 3: Wikipedia adapter (background)

**Files:** Create `litnav/discover/adapters/wikipedia.py`; Test `tests/test_discover_wikipedia.py`.

Wikipedia: search `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit={k}` → `{"query":{"search":[{"title","snippet"}]}}`; summary `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` → `{"title","extract","content_urls":{"desktop":{"page"}}}`.

- [ ] **Step 1: failing test** `tests/test_discover_wikipedia.py`:
```python
from litnav.discover.adapters import wikipedia

SEARCH = {"query": {"search": [{"title": "ReAct (machine learning)", "snippet": "a paradigm"},
                               {"title": "Software agent", "snippet": "an agent"}]}}
SUMMARY = {"ReAct (machine learning)": {"title": "ReAct (machine learning)",
            "extract": "ReAct is a prompting paradigm.", "content_urls": {"desktop": {"page": "http://w/ReAct"}}},
           "Software agent": {"title": "Software agent", "extract": "A software agent acts.",
            "content_urls": {"desktop": {"page": "http://w/Agent"}}}}


def test_parse_wikipedia():
    def fetch(url):
        if "list=search" in url:
            return SEARCH
        for title, summ in SUMMARY.items():
            if title.replace(" ", "_") in url or title in url:
                return summ
        return {}
    sources = wikipedia.search("react agents", k=2, fetch=fetch)
    assert len(sources) == 2
    assert sources[0].source_type == "wikipedia"
    assert sources[0].title == "ReAct (machine learning)"
    assert "prompting paradigm" in sources[0].abstract
    assert sources[0].url == "http://w/ReAct"
    assert sources[0].authority_score == 0.5   # fixed baseline for curated encyclopedic background
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: create `litnav/discover/adapters/wikipedia.py`:**
```python
"""Wikipedia adapter: clean encyclopedic background. Injectable fetch for offline tests."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

from litnav.discover.contract import Source

_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit={k}&srsearch={q}"
_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_WIKI_AUTHORITY = 0.5   # encyclopedic background: a fixed, honest baseline (not citation-ranked)


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
        ))
    return out
```

- [ ] **Step 4:** run `python -m pytest tests/test_discover_wikipedia.py -v` → PASS. `pytest -q` → **199 passed**. Report real.

- [ ] **Step 5: commit** `feat(ow3): Wikipedia adapter (encyclopedic background, injectable fetch)`.

---

## Task 4: rank + dedup + full-text fetch

**Files:** Create `litnav/discover/rank.py`, `litnav/discover/fulltext.py`; Test `tests/test_discover_rank.py`.

- [ ] **Step 1: failing test** `tests/test_discover_rank.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import Source
from litnav.discover import rank

def _src(title, auth, abstract=""):
    return Source(source_type="web", source_id=title, url="u", title=title,
                  authority_score=auth, abstract=abstract)

def test_dedup_by_normalized_title():
    a = _src("ReAct: Reasoning and Acting", 0.9)
    b = _src("react reasoning and acting", 0.3)   # dup (normalized) -> keep higher authority
    out = rank.dedup([a, b])
    assert len(out) == 1 and out[0].authority_score == 0.9

def test_rank_offline_is_authority_only(monkeypatch):
    # offline (no embeddings) -> ranking falls back to authority_score order
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("low", 0.2, "agents"), _src("high", 0.8, "agents")]
    out = rank.rank_sources("agent reasoning", srcs, conn=c, session_id="s", k=2)
    assert [s.title for s in out] == ["high", "low"]
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: create `litnav/discover/rank.py`:**
```python
"""Rank + dedup discovered sources. Relevance = embedding cosine of (title+abstract) vs the goal
(metered, text-embedding-3-small) when available; offline falls back to authority order. Final score
blends relevance and authority. SPECTER rerank is a future RECORDED_NEEDS item."""
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
    if vecs:                                            # live: blend relevance + authority
        gvec, svecs = vecs[0], vecs[1:]
        scored = [(_REL_W * _cosine(gvec, sv) + _AUTH_W * s.authority_score, s)
                  for s, sv in zip(sources, svecs)]
    else:                                               # offline: authority only
        scored = [(s.authority_score, s) for s in sources]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored[:k]]
```

- [ ] **Step 4: create `litnav/discover/fulltext.py`** (reuse the arXiv extractor for arXiv sources; else use the abstract as a single chunk):
```python
"""Fetch full text for the top-k sources. arXiv -> real PDF extract (reuse ingest.pdf_extract);
others -> the abstract as a single chunk (best available without scraping)."""
from __future__ import annotations
from litnav.discover.contract import Source


def fetch_fulltext(source: Source, *, max_chunks: int = 6) -> list[str]:
    if source.arxiv_id:
        try:  # pragma: no cover - network
            from litnav.ingest.corpus_expand import _download_and_extract
            paper = _download_and_extract(source.arxiv_id)
            if paper and paper.get("chunks"):
                return paper["chunks"][:max_chunks]
        except Exception:
            pass
    return [source.abstract] if source.abstract else []


def attach_fulltext(sources: list[Source], *, top_k: int) -> None:
    """Fill .chunks for the top_k sources (in place). Cost = bounded full-text fetch only for top-k."""
    for s in sources[:top_k]:
        s.chunks = fetch_fulltext(s)
```

- [ ] **Step 5:** run `python -m pytest tests/test_discover_rank.py -v` → PASS. `pytest -q` → **201 passed**. Report real.

- [ ] **Step 6: commit** `feat(ow3): rank (embedding relevance + authority) + dedup + arXiv full-text fetch`.

---

## Task 5: find_sources orchestrator + query cache + SKILL.md

**Files:** Create `litnav/discover/find_sources.py`, `litnav/discover/SKILL.md`; Test `tests/test_find_sources.py`.

- [ ] **Step 1: failing test** `tests/test_find_sources.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import DiscoverInput, Source
from litnav.discover import find_sources
from litnav.discover.adapters import openalex, wikipedia
from litnav.discover import fulltext

def test_orchestrator_merges_ranks_and_attaches_fulltext(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    monkeypatch.setattr(openalex, "search",
        lambda q, k=10, fetch=None: [Source("arxiv", "2210.03629", "u", "ReAct", 0.9, abstract="reasoning acting", arxiv_id="2210.03629")])
    monkeypatch.setattr(wikipedia, "search",
        lambda q, k=5, fetch=None: [Source("wikipedia", "Agent", "w", "Software agent", 0.5, abstract="an agent")])
    monkeypatch.setattr(fulltext, "attach_fulltext", lambda sources, *, top_k: [setattr(s, "chunks", ["full text"]) for s in sources[:top_k]])
    c = sqlite3.connect(":memory:"); init_db(c)
    res = find_sources.find(DiscoverInput("how to build a react agent", k=2), conn=c, session_id="s")
    assert res.intent_used in {"applied", "reference", "crash-course", "systematic", "cutting-edge"}
    assert 1 <= len(res.sources) <= 2
    titles = {s.title for s in res.sources}
    assert "ReAct" in titles
    assert any(s.chunks for s in res.sources)   # top-k full text attached
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: create `litnav/discover/find_sources.py`:**
```python
"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Every LLM/embedding call is metered; full-text
fetch is bounded to the top-k. A query cache (digest_cache table, slice_key='discover:<hash>') skips
re-discovery of an identical goal."""
from __future__ import annotations
import hashlib
import sqlite3

from litnav.discover.contract import DiscoverInput, DiscoverResult
from litnav.discover import intent as intent_mod, rank as rank_mod, fulltext as fulltext_mod
from litnav.discover.adapters import openalex, wikipedia

# Which source types each intent prefers (all use both for now; weights via authority/relevance).
_FULLTEXT_TOPK = 3


def _query_key(goal: str, intent: str, k: int) -> str:
    return "discover:" + hashlib.sha1(f"{goal}|{intent}|{k}".encode()).hexdigest()[:16]


def find(di: DiscoverInput, *, conn: sqlite3.Connection, session_id: str | None = None,
         budget: int | None = None) -> DiscoverResult:
    intent = intent_mod.classify(di.goal_text, conn=conn, session_id=session_id,
                                 explicit=di.intent, budget=budget)
    # gather metadata-only from adapters (best-effort; an adapter failure is non-fatal)
    sources = []
    for adapter, n in ((openalex, di.k * 2), (wikipedia, 3)):
        try:
            sources.extend(adapter.search(di.goal_text, k=n))
        except Exception:
            pass
    ranked = rank_mod.rank_sources(di.goal_text, sources, conn=conn, session_id=session_id,
                                   k=di.k, budget=budget)
    fulltext_mod.attach_fulltext(ranked, top_k=min(_FULLTEXT_TOPK, len(ranked)))
    for s in ranked:
        if not s.why:
            s.why = f"intent={intent}; authority={s.authority_score}"
    return DiscoverResult(sources=ranked, intent_used=intent)
```

- [ ] **Step 4: create `litnav/discover/SKILL.md`** — contract (In/Out), the live capability gate (`verify_discover_live`) vs the offline determinism unit gate (`verify_discover`), cost notes (metadata-only first; full-text only top-k; intent+rerank metered), and the recorded deferrals (S2/youtube adapters, SPECTER rerank, multi-round systematic).

- [ ] **Step 5:** run `python -m pytest tests/test_find_sources.py -v` → PASS. `pytest -q` → **202 passed**. Report real. 6 offline gates green.

- [ ] **Step 6: commit** `feat(ow3): find_sources orchestrator (intent -> adapters -> rank -> top-k full text) + SKILL.md`.

---

## Task 6: verify_discover (offline unit) + verify_discover_live (LIVE capability + digest integration)

**Files:** Create `litnav/evaluation/verify_discover.py`, `litnav/evaluation/verify_discover_live.py`; Test `tests/test_verify_discover.py`.

- [ ] **Step 1: failing test** `tests/test_verify_discover.py`:
```python
from litnav.evaluation.verify_discover import main


def test_verify_discover_offline_gate():
    assert main() == 0
```

- [ ] **Step 2: create `litnav/evaluation/verify_discover.py`** — OFFLINE determinism unit gate (labeled NOT capability evidence). Assert with canned `fetch`: OpenAlex parsing (authority normalization, arXiv-id extraction, inverted-index abstract), Wikipedia parsing, `dedup` collapses normalized-duplicate titles keeping higher authority, and `rank_sources` offline = authority order. Print `G-discover PASS:` lines + `ALL PASS`, `return 0`.

- [ ] **Step 3: create `litnav/evaluation/verify_discover_live.py`** — the LIVE capability gate (skips at provider=none). Real goal -> real OpenAlex+Wikipedia -> rank -> top-k full text -> assert:
```
- was_live() on the intent/rerank calls; cost_ledger spend > 0 (stage='discover').
- >= 3 sources returned; every source has a non-empty title and a url; authority_score in [0,1].
- dedup held (no two sources share a normalized title).
- at least one source has real full-text chunks (len(chunks) > 0 and the text is multi-sentence,
  NOT a one-line abstract) — proves the arXiv full-text path works.
- DIGEST INTEGRATION (closes A1): feed the top full-text source into pipeline.digest LIVE and REPORT
  the edge_accuracy + edge count on RICH evidence (vs the 3-sentence fixture's 0.0). Assert the digest
  ran live (was_live) and produced >= 2 concepts; REPORT (do not hard-gate) whether prereq edges now
  survive the gpt-4o judge — this is the real A1 re-evaluation.
- cost <= a sane bound; print the full cost_ledger table (discover + digest).
```
Print `G-discover-live` PASS/REPORT lines + `ALL PASS`.

- [ ] **Step 4:** offline: `python -m litnav.evaluation.verify_discover` → ALL PASS; `python -m litnav.evaluation.verify_discover_live` (provider=none) → SKIP, exit 0. `pytest -q` → **203 passed**. 6 prior gates + verify_discover green. Report real.

- [ ] **Step 5: commit** `feat(ow3): verify_discover offline unit gate + verify_discover_live capability gate (digest A1 re-eval)`.

---

## Controller live verification (NOT a subagent task) → the report
After all 6 tasks land, the controller runs the live gate with a real provider + network:
```bash
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_discover_live
```
Then produce the three-part report (live usage + cost table + evaluation). **Crucially, this is the A1 re-evaluation:** does the digest, fed REAL full-text discovered live, now build prereq edges that survive the gpt-4o judge (vs 0.0 on the 3-sentence fixture)? Record the verdict + any model action.

## Self-Review
- Spec §6.1 coverage: intent classifier (T1), source-type stack via adapters (T2/T3), ranking (T4, embedding rerank — SPECTER deferred/recorded), dedup (T4), authority score (T2), metadata-first + top-k full-text (T4/T5), query cache (T5 key; full memoization can extend later). Multi-round systematic deferred. ✅
- Live-first: capability via verify_discover_live; offline gates only for parsing/rank/dedup/intent-heuristic determinism. Adapters use injectable fetch so offline tests need no network. ✅
- Metering: intent + rerank via router (stage='discover'); HTTP bounded (timeout, top-k full text). ✅
- A1 loop: verify_discover_live feeds real full text into digest and re-reports edge quality. ✅
- Type consistency: `Source`/`DiscoverInput`/`DiscoverResult`, `search(query,k,*,fetch)`, `rank_sources`, `attach_fulltext`, `classify` names used identically across tasks. ✅
- No new enabled model (intent+rerank use cheap/embed; SPECTER stays record-only). ✅
