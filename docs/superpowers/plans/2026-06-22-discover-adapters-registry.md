# DISCOVER Adapter Registry + New Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a selectable-adapter registry and two new search adapters (Semantic Scholar and arXiv direct-search) to the LitNavigator DISCOVER subsystem, wired into `find_sources.py` with a `selected_adapters` opt-in parameter.

**Architecture:** A new `litnav/discover/adapters/registry.py` holds a list of `AdapterDescriptor` dataclasses (id, name, description, default_on, intent_affinity, search fn). `find_sources.py` resolves the adapter set from `DiscoverInput.selected_adapters` via `registry.resolve()`, replacing the current hard-coded `(openalex, wikipedia)` loop. Two new adapter files (`semantic_scholar.py`, `arxiv.py`) follow the existing injectable-fetch pattern.

**Tech Stack:** Python stdlib only (urllib, xml.etree.ElementTree, math, json, dataclasses). No new dependencies. venv: `.venv/bin/python`. Test runner: pytest.

## Global Constraints

- Touch ONLY `litnav/discover/` (contract.py, find_sources.py, adapters/__init__.py, adapters/registry.py, adapters/semantic_scholar.py, adapters/arxiv.py) and `tests/` (test_adapter_registry.py, test_new_adapters.py)
- Do NOT edit `litnav/ui/*`, `interactive.py`, or `server.py`
- All new code must be importable offline (no network calls at module import)
- Adapter outages are non-fatal (try/except in find_sources.py)
- Mastery/routing decisions are never inside adapters — adapters return `list[Source]` only
- Use `.venv/bin/python -m pytest -q` to run the full suite; must stay green throughout
- Branch: `feat/usability-revamp` — commit there

---

### Task 1: Adapter registry

**Files:**
- Create: `litnav/discover/adapters/registry.py`
- Modify: `litnav/discover/adapters/__init__.py` (re-export `available_adapters`, `resolve`)
- Test: `tests/test_adapter_registry.py`

**Interfaces:**
- Produces:
  - `AdapterDescriptor` dataclass with fields: `id: str`, `name: str`, `description: str`, `default_on: bool`, `intent_affinity: list[str]`, `search: Callable[[str, int], list[Source]]`
  - `available_adapters() -> list[AdapterDescriptor]` — returns all registered descriptors
  - `resolve(selected_ids: list[str] | None) -> list[AdapterDescriptor]` — `None` or empty → all `default_on`; non-empty → descriptors matching those ids (unknown ids silently dropped)

- [ ] **Step 1: Write the failing tests**

`tests/test_adapter_registry.py`:
```python
from litnav.discover.adapters import registry


def test_available_adapters_has_at_least_four():
    ads = registry.available_adapters()
    assert len(ads) >= 4


def test_descriptor_has_required_fields():
    for ad in registry.available_adapters():
        assert ad.id and isinstance(ad.id, str)
        assert ad.name and isinstance(ad.name, str)
        assert ad.description and isinstance(ad.description, str)
        assert isinstance(ad.default_on, bool)
        assert isinstance(ad.intent_affinity, list)
        assert callable(ad.search)


def test_resolve_none_returns_default_on():
    result = registry.resolve(None)
    default_ids = {ad.id for ad in registry.available_adapters() if ad.default_on}
    result_ids = {ad.id for ad in result}
    assert result_ids == default_ids


def test_resolve_empty_returns_default_on():
    result = registry.resolve([])
    default_ids = {ad.id for ad in registry.available_adapters() if ad.default_on}
    result_ids = {ad.id for ad in result}
    assert result_ids == default_ids


def test_resolve_specific_id():
    result = registry.resolve(["arxiv"])
    assert len(result) == 1
    assert result[0].id == "arxiv"


def test_resolve_unknown_id_silently_dropped():
    result = registry.resolve(["arxiv", "nonexistent_id_xyz"])
    assert len(result) == 1
    assert result[0].id == "arxiv"


def test_resolve_multiple_ids():
    result = registry.resolve(["openalex", "wikipedia"])
    result_ids = {ad.id for ad in result}
    assert result_ids == {"openalex", "wikipedia"}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_adapter_registry.py -q
```
Expected: ImportError or AttributeError (registry module doesn't exist yet).

- [ ] **Step 3: Implement `registry.py`**

`litnav/discover/adapters/registry.py`:
```python
"""Selectable-adapter registry for DISCOVER.

Each AdapterDescriptor exposes UI-facing metadata (id, name, description,
default_on, intent_affinity) plus a `search` callable so callers never need
to import adapter modules directly.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

from litnav.discover.contract import Source
from litnav.discover.adapters import openalex, wikipedia, semantic_scholar, arxiv


@dataclass
class AdapterDescriptor:
    id: str
    name: str
    description: str
    default_on: bool
    intent_affinity: list[str]
    search: Callable[[str, int], list[Source]]


_REGISTRY: list[AdapterDescriptor] = [
    AdapterDescriptor(
        id="openalex",
        name="OpenAlex",
        description="200M+ scholarly works; citation-based authority scoring.",
        default_on=True,
        intent_affinity=["crash-course", "systematic", "applied", "reference", "cutting-edge"],
        search=openalex.search,
    ),
    AdapterDescriptor(
        id="wikipedia",
        name="Wikipedia",
        description="Encyclopedic background; good for concept overviews.",
        default_on=True,
        intent_affinity=["crash-course", "reference"],
        search=wikipedia.search,
    ),
    AdapterDescriptor(
        id="semantic_scholar",
        name="Semantic Scholar",
        description="ML-ranked scholarly search with TLDRs; fixes tangential-paper problem.",
        default_on=True,
        intent_affinity=["crash-course", "systematic", "applied", "reference", "cutting-edge"],
        search=semantic_scholar.search,
    ),
    AdapterDescriptor(
        id="arxiv",
        name="arXiv Direct Search",
        description="Preprint relevance search; surfaces recent ML/CS papers before peer review.",
        default_on=True,
        intent_affinity=["cutting-edge", "systematic"],
        search=arxiv.search,
    ),
]


def available_adapters() -> list[AdapterDescriptor]:
    """Return all registered adapter descriptors."""
    return list(_REGISTRY)


def resolve(selected_ids: list[str] | None) -> list[AdapterDescriptor]:
    """Return adapters for the given id list, or all default_on if None/empty."""
    if not selected_ids:
        return [ad for ad in _REGISTRY if ad.default_on]
    id_set = set(selected_ids)
    return [ad for ad in _REGISTRY if ad.id in id_set]
```

- [ ] **Step 4: Update `adapters/__init__.py`**

`litnav/discover/adapters/__init__.py`:
```python
"""DISCOVER source adapters."""
from litnav.discover.adapters.registry import available_adapters, resolve, AdapterDescriptor

__all__ = ["available_adapters", "resolve", "AdapterDescriptor"]
```

Note: This imports registry which imports semantic_scholar and arxiv — those must exist before this step. We'll add stubs first, then fill them in Task 2 and 3.

Actually, create minimal stubs now so the registry import doesn't fail:

`litnav/discover/adapters/semantic_scholar.py` (stub — will be replaced in Task 2):
```python
"""Semantic Scholar adapter stub — full implementation in Task 2."""
from litnav.discover.contract import Source


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:  # pragma: no cover
    return []
```

`litnav/discover/adapters/arxiv.py` (stub — will be replaced in Task 3):
```python
"""arXiv direct-search adapter stub — full implementation in Task 3."""
from litnav.discover.contract import Source


def search(query: str, k: int = 10, *, fetch=None) -> list[Source]:  # pragma: no cover
    return []
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_adapter_registry.py -q
```
Expected: 7 tests PASS.

- [ ] **Step 6: Run full suite to confirm nothing broken**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest -q
```
Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add litnav/discover/adapters/registry.py litnav/discover/adapters/__init__.py \
        litnav/discover/adapters/semantic_scholar.py litnav/discover/adapters/arxiv.py \
        tests/test_adapter_registry.py
git commit -m "feat(discover): selectable-adapter registry + metadata"
```

---

### Task 2: Semantic Scholar adapter

**Files:**
- Modify: `litnav/discover/adapters/semantic_scholar.py` (replace stub)
- Test: `tests/test_new_adapters.py` (create; will also contain arXiv tests in Task 3)

**Interfaces:**
- Consumes: `AdapterDescriptor.search` signature = `search(query: str, k: int, *, fetch=None) -> list[Source]`
- Produces: `semantic_scholar.search(query, k, *, fetch=None) -> list[Source]`
  - `source_type`: `"arxiv"` if `externalIds.ArXiv` present, else `"web"`
  - `source_id`: S2 paperId
  - `url`: `openAccessPdf.url` if present, else `f"https://www.semanticscholar.org/paper/{paperId}"`
  - `title`: `title` field
  - `abstract`: `abstract` field, falling back to `tldr.text` if abstract is None/empty
  - `authority_score`: `_authority(citationCount)` — same log formula as openalex
  - `arxiv_id`: `externalIds.get("ArXiv")` (may be None)

**API endpoint:** `https://api.semanticscholar.org/graph/v1/paper/search?query=...&fields=title,abstract,tldr,citationCount,externalIds,openAccessPdf,year&limit=k`

**Rate limit:** ~1 RPS shared (no key). Non-fatal on 429/outage (caller wraps in try/except). The adapter itself does NOT implement rate limiting; it just makes one request.

**Sample API response for test:**
```json
{
  "data": [
    {
      "paperId": "abc123",
      "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
      "abstract": "We explore the use of LLMs to generate reasoning traces.",
      "tldr": {"model": "tldr@v2.0.0", "text": "A method combining reasoning and acting."},
      "citationCount": 2500,
      "externalIds": {"ArXiv": "2210.03629"},
      "openAccessPdf": {"url": "https://arxiv.org/pdf/2210.03629", "status": "GREEN"},
      "year": 2022
    },
    {
      "paperId": "def456",
      "title": "No Abstract Paper",
      "abstract": null,
      "tldr": {"model": "tldr@v2.0.0", "text": "Short summary only."},
      "citationCount": 50,
      "externalIds": {},
      "openAccessPdf": null,
      "year": 2023
    }
  ],
  "total": 2,
  "offset": 0,
  "next": 2
}
```

- [ ] **Step 1: Write the failing Semantic Scholar tests**

`tests/test_new_adapters.py`:
```python
"""Tests for Semantic Scholar and arXiv adapters. No network calls — inject fake fetch."""
import urllib.parse
from litnav.discover.adapters import semantic_scholar, arxiv

# ── Semantic Scholar ──────────────────────────────────────────────────────────

S2_CANNED = {
    "data": [
        {
            "paperId": "abc123",
            "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
            "abstract": "We explore the use of LLMs to generate reasoning traces.",
            "tldr": {"model": "tldr@v2.0.0", "text": "A method combining reasoning and acting."},
            "citationCount": 2500,
            "externalIds": {"ArXiv": "2210.03629"},
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2210.03629", "status": "GREEN"},
            "year": 2022,
        },
        {
            "paperId": "def456",
            "title": "No Abstract Paper",
            "abstract": None,
            "tldr": {"model": "tldr@v2.0.0", "text": "Short summary only."},
            "citationCount": 50,
            "externalIds": {},
            "openAccessPdf": None,
            "year": 2023,
        },
    ],
    "total": 2,
    "offset": 0,
    "next": 2,
}


def test_s2_parse_results():
    sources = semantic_scholar.search("react agents", k=10, fetch=lambda url: S2_CANNED)
    assert len(sources) == 2

    s0 = sources[0]
    assert s0.title.startswith("ReAct")
    assert s0.source_type == "arxiv"
    assert s0.arxiv_id == "2210.03629"
    assert s0.source_id == "abc123"
    assert "LLMs" in s0.abstract
    assert s0.url == "https://arxiv.org/pdf/2210.03629"
    assert 0.0 < s0.authority_score <= 1.0

    s1 = sources[1]
    assert s1.source_type == "web"
    assert s1.arxiv_id is None
    # abstract falls back to tldr.text when abstract is None
    assert "Short summary only" in s1.abstract
    assert "semanticscholar.org" in s1.url


def test_s2_url_has_query_and_fields():
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"data": []}
    semantic_scholar.search("multi agent debate", k=5, fetch=fake)
    u = captured["url"]
    assert "paper/search" in u
    assert "query=" in u
    assert "fields=" in u
    assert "limit=5" in u


def test_s2_authority_zero_citations():
    canned = {"data": [{"paperId": "z1", "title": "Zero Cites", "abstract": "x",
                         "tldr": None, "citationCount": 0, "externalIds": {},
                         "openAccessPdf": None, "year": 2024}]}
    s = semantic_scholar.search("q", k=1, fetch=lambda url: canned)[0]
    assert s.authority_score == 0.0


def test_s2_tldr_fallback_when_no_abstract():
    canned = {"data": [{"paperId": "z2", "title": "T", "abstract": "",
                         "tldr": {"text": "TLDR text here."}, "citationCount": 10,
                         "externalIds": {}, "openAccessPdf": None, "year": 2024}]}
    s = semantic_scholar.search("q", k=1, fetch=lambda url: canned)[0]
    assert s.abstract == "TLDR text here."


# ── arXiv ─────────────────────────────────────────────────────────────────────

ARXIV_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2210.03629v1</id>
    <title>ReAct: Synergizing Reasoning and Acting</title>
    <summary>We explore reasoning traces and acting in LLMs.</summary>
    <author><name>Shunyu Yao</name></author>
    <link href="http://arxiv.org/pdf/2210.03629v1" rel="related" type="application/pdf"/>
    <link href="http://arxiv.org/abs/2210.03629v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2305.14325v2</id>
    <title>Toolformer: Language Models Can Teach Themselves to Use Tools</title>
    <summary>We introduce Toolformer, a model trained to use APIs.</summary>
    <author><name>Timo Schick</name></author>
    <link href="http://arxiv.org/abs/2305.14325v2" rel="alternate" type="text/html"/>
  </entry>
</feed>"""


def test_arxiv_parse_results():
    sources = arxiv.search("react agents", k=5, fetch=lambda url: ARXIV_ATOM)
    assert len(sources) == 2

    s0 = sources[0]
    assert s0.title == "ReAct: Synergizing Reasoning and Acting"
    assert s0.source_type == "arxiv"
    assert s0.arxiv_id == "2210.03629"
    assert s0.source_id == "2210.03629"
    assert "reasoning traces" in s0.abstract
    assert s0.authority_score == 0.35
    assert s0.url is not None and "arxiv.org" in s0.url

    s1 = sources[1]
    assert s1.arxiv_id == "2305.14325"
    assert "Toolformer" in s1.title


def test_arxiv_url_has_search_query():
    captured = {}
    def fake(url):
        captured["url"] = url
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    arxiv.search("multi agent debate", k=3, fetch=fake)
    u = captured["url"]
    assert "export.arxiv.org" in u
    assert "max_results=3" in u
    assert "search_query=" in u


def test_arxiv_source_type_is_arxiv():
    sources = arxiv.search("q", k=5, fetch=lambda url: ARXIV_ATOM)
    assert all(s.source_type == "arxiv" for s in sources)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_new_adapters.py -q
```
Expected: Failures — stubs return empty lists so assertions on source content fail.

- [ ] **Step 3: Implement `semantic_scholar.py`**

`litnav/discover/adapters/semantic_scholar.py`:
```python
"""Semantic Scholar adapter: ML-ranked scholarly search with TLDRs.
Injectable `fetch` for offline testing; live uses real HTTP.
Rate limit: ~1 RPS shared (no key). Non-fatal on 429/outage — caller wraps in try/except."""
from __future__ import annotations
import json
import math
import urllib.parse
import urllib.request

from litnav.discover.contract import Source

_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,abstract,tldr,citationCount,externalIds,openAccessPdf,year"
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
        ))
    return out
```

- [ ] **Step 4: Run the S2 tests to confirm they pass**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_new_adapters.py -k "s2" -q
```
Expected: 4 S2 tests PASS.

---

### Task 3: arXiv direct-search adapter

**Files:**
- Modify: `litnav/discover/adapters/arxiv.py` (replace stub)
- Test: `tests/test_new_adapters.py` (already has arXiv tests from Task 2 step 1)

**Interfaces:**
- Produces: `arxiv.search(query: str, k: int, *, fetch=None) -> list[Source]`
  - `fetch(url)` returns `bytes` (raw Atom XML) — note this is different from JSON adapters
  - `source_type`: always `"arxiv"`
  - `source_id`: arXiv ID extracted from `<entry>/<id>` (e.g., `2210.03629` from `http://arxiv.org/abs/2210.03629v1`)
  - `arxiv_id`: same as `source_id`
  - `url`: PDF link from `<link rel="related" type="application/pdf">` if present, else `<link rel="alternate">` (abstract page)
  - `abstract`: text of `<summary>` element
  - `title`: text of `<title>` element
  - `authority_score`: `0.35` fixed

**API endpoint:** `http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={k}&sortBy=relevance`

**XML namespace:** `{http://www.w3.org/2005/Atom}` — all elements are in this namespace.

- [ ] **Step 1: Implement `arxiv.py`**

`litnav/discover/adapters/arxiv.py`:
```python
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
```

- [ ] **Step 2: Run all new adapter tests**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_new_adapters.py -q
```
Expected: all 9 tests PASS.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest -q
```
Expected: all tests green.

- [ ] **Step 4: Commit**

```bash
git add litnav/discover/adapters/semantic_scholar.py litnav/discover/adapters/arxiv.py \
        tests/test_new_adapters.py
git commit -m "feat(discover): Semantic Scholar + arXiv-direct search adapters"
```

---

### Task 4: Wire registry into `find_sources.py` + extend `DiscoverInput`

**Files:**
- Modify: `litnav/discover/contract.py` (add `selected_adapters` field)
- Modify: `litnav/discover/find_sources.py` (replace hard-coded adapter loop with registry resolution)
- Test: `tests/test_verify_discover.py` (existing; must stay green) + add one integration test in `tests/test_adapter_registry.py`

**Interfaces:**
- Consumes: `registry.resolve(selected_ids) -> list[AdapterDescriptor]`; `ad.search(query, n)` callable
- Produces: `DiscoverInput.selected_adapters: list[str] | None = None`; `find()` accepts it transparently

- [ ] **Step 1: Add the integration test first**

Append to `tests/test_adapter_registry.py`:
```python
from litnav.discover.contract import DiscoverInput


def test_discover_input_has_selected_adapters_field():
    di = DiscoverInput(goal_text="test")
    assert di.selected_adapters is None   # default

    di2 = DiscoverInput(goal_text="test", selected_adapters=["arxiv"])
    assert di2.selected_adapters == ["arxiv"]
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest tests/test_adapter_registry.py::test_discover_input_has_selected_adapters_field -q
```
Expected: AssertionError — `DiscoverInput` doesn't have `selected_adapters` yet.

- [ ] **Step 3: Add `selected_adapters` to `DiscoverInput`**

Edit `litnav/discover/contract.py` — add `selected_adapters` field to the dataclass:
```python
"""Typed contract for find-sources (DISCOVER)."""
from __future__ import annotations
from dataclasses import dataclass, field

INTENTS = {"crash-course", "systematic", "applied", "reference", "cutting-edge"}


@dataclass
class DiscoverInput:
    goal_text: str
    intent: str | None = None
    budget: int | None = None
    k: int = 6
    selected_adapters: list[str] | None = None


@dataclass
class Source:
    source_type: str
    source_id: str
    url: str | None
    title: str
    authority_score: float = 0.0
    why: str = ""
    abstract: str = ""
    arxiv_id: str | None = None
    chunks: list[str] = field(default_factory=list)


@dataclass
class DiscoverResult:
    sources: list[Source]
    intent_used: str
    cache_hit: bool = False
```

- [ ] **Step 4: Update `find_sources.py` to use the registry**

Replace the hard-coded adapter loop in `find_sources.py`. The full new file:
```python
"""DISCOVER orchestrator: classify intent -> query adapters (metadata only) -> rank + dedup ->
attach full text for the top-k -> DiscoverResult. Adapter failures are non-fatal. Every LLM/embedding
call is metered; full-text fetch is bounded to the top-k."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import sqlite3

from litnav.discover.contract import DiscoverInput, DiscoverResult, Source
from litnav.discover import intent as intent_mod, rank as rank_mod, fulltext as fulltext_mod
from litnav.discover import relevance as relevance_mod
from litnav.discover import query as query_mod
from litnav.discover.adapters import registry as adapter_registry
from litnav.storage import openworld_repo

_FULLTEXT_TOPK = 3
_WIKIPEDIA_K = 3   # Wikipedia always fetches a smaller set


def _query_key(di: DiscoverInput) -> str:
    raw = f"{di.goal_text}|{di.k}"
    return "discover:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def find(di: DiscoverInput, *, conn: sqlite3.Connection, session_id: str | None = None,
         budget: int | None = None) -> DiscoverResult:
    key = _query_key(di)
    cached = openworld_repo.discover_cache_get(conn, key)
    if cached is not None:
        data = json.loads(cached)
        sources = [Source(**s) for s in data["sources"]]
        return DiscoverResult(sources=sources, intent_used=data["intent_used"], cache_hit=True)

    sq = query_mod.to_search_query(di.goal_text, conn=conn, session_id=session_id, budget=budget)
    intent = intent_mod.classify(di.goal_text, conn=conn, session_id=session_id,
                                 explicit=di.intent, budget=budget)

    adapters = adapter_registry.resolve(di.selected_adapters)
    sources = []
    for ad in adapters:
        # Wikipedia historically gets a smaller k to avoid flooding results
        n = _WIKIPEDIA_K if ad.id == "wikipedia" else di.k * 2
        try:
            sources.extend(ad.search(sq, k=n))
        except Exception:
            pass                                   # an adapter outage is non-fatal

    ranked = rank_mod.rank_sources(sq, sources, conn=conn, session_id=session_id,
                                   k=di.k, budget=budget)
    # A14: gate on the ORIGINAL goal (full specificity — e.g. "Raft" not just "consensus") so
    # same-family-but-different sources (PBFT, QLoRA, vision-attention) are rejected, not just films.
    ranked = relevance_mod.relevance_gate(di.goal_text, ranked, conn=conn, session_id=session_id,
                                          budget=budget, min_keep=min(2, len(ranked)))
    fulltext_mod.attach_fulltext(ranked, top_k=min(_FULLTEXT_TOPK, len(ranked)))
    for s in ranked:
        if not s.why:
            s.why = f"intent={intent}; authority={s.authority_score}"

    result_json = json.dumps({
        "sources": [dataclasses.asdict(s) for s in ranked],
        "intent_used": intent,
    })
    openworld_repo.discover_cache_put(conn, key, result_json)
    return DiscoverResult(sources=ranked, intent_used=intent, cache_hit=False)
```

- [ ] **Step 5: Run full suite**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python -m pytest -q
```
Expected: all tests green (the existing `test_verify_discover.py` passes because `find()` signature is backward compatible — `selected_adapters` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add litnav/discover/contract.py litnav/discover/find_sources.py \
        tests/test_adapter_registry.py
git commit -m "feat(discover): wire registry into find_sources + selected_adapters param"
```

---

### Task 5: Live smoke test (optional, informational)

**Files:**
- Create (temporary, not committed): `/tmp/litnav_smoke.py`

**Purpose:** Confirm the adapters produce real results from the live APIs. Run manually; do NOT start a web server.

- [ ] **Step 1: Run the smoke script**

```bash
cd /Users/jingyen/GitHub/LitNavigator && .venv/bin/python - <<'EOF'
from litnav.discover.adapters import semantic_scholar, arxiv

print("=== Semantic Scholar: 'retrieval augmented generation' ===")
try:
    for s in semantic_scholar.search("retrieval augmented generation", 3):
        print(f"  [{s.source_type}] {s.title} (auth={s.authority_score})")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=== arXiv: 'ReAct language agent' ===")
try:
    for s in arxiv.search("ReAct language agent", 3):
        print(f"  [{s.source_type}] {s.title} (arxiv_id={s.arxiv_id})")
except Exception as e:
    print(f"  ERROR: {e}")
EOF
```

- [ ] **Step 2: Record titles in the task report**

Note the printed titles — confirm they are topically relevant to the query.

---

## Post-Implementation Checks

After all tasks complete:

1. Run the full suite one final time: `.venv/bin/python -m pytest -q` — must be green
2. Confirm commits: `git log --oneline -6`
3. Verify registry returns 4 adapters: `.venv/bin/python -c "from litnav.discover.adapters import registry; print([a.id for a in registry.available_adapters()])"`
