# Multi-source Digest + Survey-priority (Fix A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the open-world concept map field-general (not one paper's jargon) by digesting the top 3 sources with a survey/Wikipedia-article backbone, and surfacing surveys in ranking.

**Architecture:** DISCOVER tags each Source `is_review`; `rank_sources` adds an intent-aware survey bonus; the Wikipedia adapter fetches the full article (not the 103-char summary); the cold-start caller feeds digest the top 3 sources (digest is already multi-source); the extract prompt nudges toward general concepts.

**Tech Stack:** Python 3.14, stdlib `urllib`, existing `litnav.discover.*` + `litnav.digest.*`, pytest. Live LLM via litellm 1.83.7.

## Global Constraints
- Always use the venv: `.venv/bin/python`. Branch: `feat/usability-revamp`.
- Offline suite (469 currently) must stay green after every task. Adapter unit tests **monkeypatch HTTP** (inject `fetch=`/sample JSON) — never hit the network.
- Soft signals only: survey boost **re-sorts, never filters**. Keep arXiv extraction depth (3 pages / `max_chunks=6`) unchanged. Top-N digest fixed at **3**.
- Live verification (needs `.env`): the adversarial DISCOVER battery (`litnav/evaluation/verify_discover_adversarial.py`) on-topic rate ≥ current ~92%, and a concept-plan sanity check.
- Spec: `docs/superpowers/specs/2026-06-23-multisource-survey-digest-design.md`.

---

## Task 1: `is_review` survey signal on Source + all adapters

**Files:**
- Modify: `litnav/discover/contract.py` (Source dataclass), `litnav/discover/adapters/{openalex,semantic_scholar,arxiv,wikipedia,stack_exchange}.py`
- Test: `tests/test_is_review_signal.py`

**Interfaces:**
- Produces: `Source.is_review: bool` (default False); a shared helper `litnav/discover/adapters/_review.py::looks_like_review(title: str) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_is_review_signal.py
from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review
from litnav.discover.adapters import openalex, semantic_scholar

def test_source_has_is_review_default_false():
    assert Source("web", "x", None, "T").is_review is False

def test_title_heuristic():
    assert looks_like_review("A Comprehensive Survey on Graph Neural Networks")
    assert looks_like_review("Deep Learning: A Review")
    assert looks_like_review("An Overview of Reinforcement Learning")
    assert not looks_like_review("Attention Is All You Need")

def test_openalex_sets_is_review_from_type():
    sample = {"results": [{"id": "https://openalex.org/W1", "title": "Neural Nets",
              "type": "review", "cited_by_count": 9, "primary_location": {}}]}
    s = openalex.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is True

def test_s2_sets_is_review_from_publicationtypes():
    sample = {"data": [{"title": "A Survey of X", "publicationTypes": ["Review"],
              "citationCount": 3, "externalIds": {}, "openAccessPdf": None}]}
    s = semantic_scholar.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is True
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/python -m pytest tests/test_is_review_signal.py -q` (import + attribute errors).

- [ ] **Step 3: Implement.** Add to `contract.py` Source (after `arxiv_id`): `is_review: bool = False`. Create `litnav/discover/adapters/_review.py`:
```python
"""Shared survey/review title heuristic for DISCOVER adapters."""
from __future__ import annotations
_REVIEW_CUES = ("survey", "review", "overview", "tutorial", "a comprehensive", "systematic literature")
def looks_like_review(title: str) -> bool:
    t = (title or "").lower()
    return any(cue in t for cue in _REVIEW_CUES)
```
Then set `is_review=` in each adapter's `Source(...)`:
- **openalex.py**: `is_review=(w.get("type") == "review") or looks_like_review(w.get("title") or "")`
- **semantic_scholar.py**: `is_review=("Review" in (p.get("publicationTypes") or [])) or looks_like_review(p.get("title") or "")` and add `publicationTypes` to `_FIELDS`.
- **arxiv.py / wikipedia.py / stack_exchange.py**: `is_review=looks_like_review(<title>)` (title heuristic only).
Import `from litnav.discover.adapters._review import looks_like_review` in each.

- [ ] **Step 4: Run, confirm PASS** — `.venv/bin/python -m pytest tests/test_is_review_signal.py -q`
- [ ] **Step 5: Commit** — `git commit -m "feat(discover): is_review survey signal on Source + all adapters (Fix A.1)"`

---

## Task 2: Intent-aware survey-priority rank boost

**Files:**
- Modify: `litnav/discover/rank.py` (`rank_sources` signature + score), `litnav/discover/find_sources.py` (pass `intent`)
- Test: `tests/test_survey_rank_boost.py`

**Interfaces:**
- Consumes: `Source.is_review` (Task 1).
- Produces: `rank_sources(..., intent: str | None = None)`; module consts `_SURVEY_BONUS` (dict by intent class) + `survey_bonus(intent) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_survey_rank_boost.py
from litnav.discover.rank import survey_bonus

def test_bonus_intent_scaled():
    assert survey_bonus("survey") >= survey_bonus(None) >= survey_bonus("cutting-edge")
    assert survey_bonus("crash-course") > survey_bonus("cutting-edge")
    assert survey_bonus("cutting-edge") >= 0.0
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/python -m pytest tests/test_survey_rank_boost.py -q`

- [ ] **Step 3: Implement.** In `rank.py` add:
```python
# Intent-aware survey bonus (soft re-sort; never a filter). Added to the rel+auth blend.
_SURVEY_BONUS = {"survey": 0.20, "crash-course": 0.20, "beginner": 0.20,
                 "cutting-edge": 0.05}
_SURVEY_BONUS_DEFAULT = 0.12
def survey_bonus(intent: str | None) -> float:
    return _SURVEY_BONUS.get((intent or "").lower(), _SURVEY_BONUS_DEFAULT)
```
Change `rank_sources` signature to add `intent: str | None = None`, and add the bonus to BOTH score branches:
```python
        scored = [(_REL_W * _cosine(gvec, sv) + _AUTH_W * s.authority_score
                   + (survey_bonus(intent) if s.is_review else 0.0), s)
                  for s, sv in zip(sources, svecs)]
    else:
        scored = [(s.authority_score + (survey_bonus(intent) if s.is_review else 0.0), s)
                  for s in sources]
```
In `find_sources.py` pass it: `rank_mod.rank_sources(sq, sources, conn=conn, session_id=session_id, k=..., budget=budget, intent=intent)`.

- [ ] **Step 4: Add a discriminating test** (review outranks equal-relevance primary for survey, less so for cutting-edge) using a fake embedder is heavy — instead assert ordering via the offline (no-conn) branch where score = authority + bonus:
```python
# tests/test_survey_rank_boost.py (append)
import sqlite3
from litnav.discover.contract import Source
from litnav.discover.rank import rank_sources
def _src(title, auth, review):
    return Source("web", title, None, title, authority_score=auth, is_review=review)
def test_review_floats_up_for_survey_intent_offline():
    prim=_src("Primary", 0.50, False); rev=_src("A Survey", 0.45, True)
    # offline (conn=None) → score = authority + survey_bonus
    out = rank_sources("graphs", [prim, rev], conn=None, session_id=None, k=2, intent="survey")
    assert out[0].title == "A Survey"               # 0.45+0.20 > 0.50
    out2 = rank_sources("graphs", [prim, rev], conn=None, session_id=None, k=2, intent="cutting-edge")
    assert out2[0].title == "Primary"               # 0.45+0.05 < 0.50
```

- [ ] **Step 5: Run PASS + full suite** — `.venv/bin/python -m pytest tests/test_survey_rank_boost.py -q && .venv/bin/python -m pytest -q`
- [ ] **Step 6: Commit** — `git commit -m "feat(discover): intent-aware survey-priority rank boost (Fix A.2)"`

---

## Task 3: Wikipedia full-article fetch

**Files:**
- Modify: `litnav/discover/adapters/wikipedia.py` (add an extracts fetch + expose it), `litnav/discover/fulltext.py` (`fetch_fulltext` uses it for wikipedia sources)
- Test: `tests/test_wikipedia_fulltext.py`

**Interfaces:**
- Produces: `wikipedia.fetch_article(title: str, *, fetch=None) -> str` (full plain-text via MediaWiki `prop=extracts&explaintext`, UA header reused; "" on failure).
- Consumes: `fulltext._chunk_text` (Task uses existing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wikipedia_fulltext.py
from litnav.discover.adapters import wikipedia
from litnav.discover.contract import Source
from litnav.discover import fulltext

_EXTRACT = {"query": {"pages": {"123": {"extract": "Graph neural networks are... " * 400}}}}

def test_fetch_article_parses_extracts():
    art = wikipedia.fetch_article("Graph neural network", fetch=lambda u: _EXTRACT)
    assert len(art) > 1000  # full body, not the 103-char summary

def test_fulltext_uses_full_article_for_wikipedia(monkeypatch):
    monkeypatch.setattr(wikipedia, "fetch_article", lambda title, **k: "Body sentence. " * 300)
    s = Source("wikipedia", "Graph_neural_network", None, "Graph neural network",
               abstract="one sentence.")
    chunks = fulltext.fetch_fulltext(s)
    assert sum(len(c) for c in chunks) > 500  # far more than the 1-sentence abstract
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/python -m pytest tests/test_wikipedia_fulltext.py -q`

- [ ] **Step 3: Implement.** In `wikipedia.py`:
```python
_EXTRACTS = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
             "&format=json&redirects=1&titles={title}")
def fetch_article(title: str, *, fetch=None) -> str:
    """Full plain-text article via MediaWiki extracts (UA header reused). '' on any failure."""
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
```
In `fulltext.py::fetch_fulltext`, before the abstract fallback, add a wikipedia branch:
```python
    if source.source_type == "wikipedia":
        from litnav.discover.adapters import wikipedia
        art = wikipedia.fetch_article(source.title)
        if art:
            return _chunk_text(art, max_chunks=max_chunks)
    return _chunk_text(source.abstract, max_chunks=max_chunks) if source.abstract else []
```
(`max_chunks` budget unchanged — the article is chunked under the same per-source cap.)

- [ ] **Step 4: Run PASS** — `.venv/bin/python -m pytest tests/test_wikipedia_fulltext.py -q`
- [ ] **Step 5: Commit** — `git commit -m "feat(discover): Wikipedia full-article fetch (extracts), not the 103-char summary (Fix A.3)"`

---

## Task 4: Multi-source digest (top-3) in the cold-start caller

**Files:**
- Modify: `litnav/ui/interactive.py` (`_build_open_world`)
- Test: `tests/test_multisource_digest_caller.py`

**Interfaces:**
- Consumes: `digest()` (already loops `di.sources`); `withft` (full-text sources). `_FULLTEXT_TOPK=3` already fills 3 sources' chunks.

- [ ] **Step 1: Write the failing test** (assert the caller builds up to 3 SourceDocs from `withft`)

```python
# tests/test_multisource_digest_caller.py
from litnav.digest.contract import SourceDoc
def _docs(withft):
    # mirrors the caller's mapping; the test pins top-3 behavior
    return [SourceDoc(s.source_type, s.source_id, s.title, s.url, s.chunks) for s in withft[:3]]
def test_top3_mapping():
    class S:  # minimal stand-in
        def __init__(s,i): s.source_type="web"; s.source_id=str(i); s.title=f"T{i}"; s.url=None; s.chunks=["x"*300]
    assert len(_docs([S(i) for i in range(5)])) == 3
    assert len(_docs([S(0)])) == 1
```
*(This pins the intended slice; the real assertion is the caller change in Step 3 — verified live in Task 6.)*

- [ ] **Step 2: Run, confirm PASS of the helper test** (it's a spec pin) — `.venv/bin/python -m pytest tests/test_multisource_digest_caller.py -q`

- [ ] **Step 3: Implement.** In `_build_open_world`, replace:
```python
        di = DigestInput(self.goal,
                         [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                         target_slugs=[])
```
with:
```python
        # Fix A: digest the top 3 full-text sources (survey/Wikipedia backbone + primaries),
        # not just the top one — digest() already ingests a list. Backbone (review/wikipedia) first.
        picks = sorted(withft[:3], key=lambda s: (not (s.is_review or s.source_type == "wikipedia")))
        di = DigestInput(self.goal,
                         [SourceDoc(s.source_type, s.source_id, s.title, s.url, s.chunks) for s in picks],
                         target_slugs=[])
```
Keep the existing `discover_done`/`source`/`digest`/`concept`/`map` streaming events (B+C) — they already iterate the real graph.

- [ ] **Step 4: Run full suite** — `.venv/bin/python -m pytest -q` (must stay green; `_build_open_world` has no offline unit test — covered live in Task 6).
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): multi-source digest — feed top-3 sources, backbone first (Fix A.4)"`

---

## Task 5: Extraction nudge toward general concepts

**Files:** Modify `litnav/digest/extract.py` (decompose prompt) · Test: `tests/test_extract_prompt_general.py`

- [ ] **Step 1: Write the failing test** (prompt contains the general-concepts instruction)
```python
# tests/test_extract_prompt_general.py
import inspect
from litnav.digest import extract
def test_prompt_nudges_general_concepts():
    src = inspect.getsource(extract.extract_concepts)
    assert "proprietary" in src.lower() or "do not use one system" in src.lower() or \
           "general, field-level" in src.lower()
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/python -m pytest tests/test_extract_prompt_general.py -q`
- [ ] **Step 3: Implement.** Add one line to the decompose prompt (after the "break it into component ideas" line):
```python
        "Prefer GENERAL, field-level concepts a learner would recognize across the field; do NOT use "
        "one system's proprietary names or acronyms as concepts (e.g. prefer 'episodic memory' over a "
        "single paper's product name). "
```
- [ ] **Step 4: Run PASS + full suite** — `.venv/bin/python -m pytest tests/test_extract_prompt_general.py -q && .venv/bin/python -m pytest -q`
- [ ] **Step 5: Commit** — `git commit -m "feat(digest): nudge extraction toward general field concepts, not one system's jargon (Fix A.5)"`

---

## Task 6: Live verification

**Files:** none (verification only); record results in `docs/eval/fix-a-verification.md`.

- [ ] **Step 1: Adversarial DISCOVER battery (live):** `PYTHONPATH=. .venv/bin/python -c "from litnav.config import load_dotenv; load_dotenv(); from litnav.evaluation.verify_discover_adversarial import main; raise SystemExit(main())"`. Expect on-topic rate ≥ ~92% (survey boost must not drop it). Record the number.
- [ ] **Step 2: Concept-plan sanity check (live):** run DISCOVER+DIGEST for "how do agents remember things across steps" (reuse a small script like the earlier live trace), print the concept names, and confirm they are **field-general** (e.g. memory types / context / retrieval), NOT one paper's jargon (TMT/TRIM). Record before/after.
- [ ] **Step 3:** full offline suite green — `.venv/bin/python -m pytest -q`.
- [ ] **Step 4: Commit** the verification note — `git commit -m "docs(eval): Fix A live verification (battery + concept-plan sanity)"`.
- [ ] **Step 5 (optional):** restart the server + re-run the 10-scenario live user-test; target > 3.3 with the narrow-plan/M4 complaints reduced.

---

## Self-Review
- **Spec coverage:** §4.1 → T1 ✓; §4.2 → T2 ✓; §4.4 Wikipedia → T3 ✓; §4.3 multi-source → T4 ✓; §4.5 extraction nudge → T5 ✓; §6 verification → T6 ✓. Decisions (top-3, soft intent-aware boost, keep extractor depth) honored.
- **Placeholders:** none — full code in each code step. T4's offline test is an explicit spec-pin (the caller is verified live), flagged honestly.
- **Type consistency:** `Source.is_review` defined T1, used T2/T4; `survey_bonus(intent)`/`rank_sources(...,intent=)` consistent T2; `wikipedia.fetch_article` defined T3, used in fulltext T3; `withft[:3]` mapping consistent T4.
- **Signatures verified against code:** `rank_sources(goal_text, sources, *, conn, session_id, k, budget)` (intent added), `_chunk_text(text,*,target_chars,max_chunks)`, `_FULLTEXT_TOPK=3`, wikipedia `_http_get_json` UA header reused, S2 `_FIELDS` extended.
