# Design — Multi-source Digest + Survey-priority (Fix A)

**Date:** 2026-06-23 · **Status:** approved (brainstorming) → ready for writing-plans
**Branch:** `feat/usability-revamp` (continue) or a fresh slice off it.

## 1. Goal & success criteria
Make the open-world concept map **field-general and sensible** instead of one paper's proprietary
jargon. Live trace for "how do agents remember across steps" produced a map of one niche paper's
internal components (TME → Task Memory Tree / TRIM / …) — the wrong altitude for the learner's goal.

**Success:** for a goal like that, the concept plan contains **general field concepts** (e.g. memory
types, context window, retrieval/RAG, episodic/semantic) rather than only one system's invented names;
the adversarial DISCOVER battery on-topic rate does not drop (ideally rises); the 10-scenario live
re-test improves on the current **3.3/5**, with the M4 "0 chunks / single paper" + narrow-plan
complaints reduced. Offline suite stays green.

## 2. Background (verified live + in code, 2026-06-23)
- `digest()` ALREADY supports multiple sources (`DigestInput.sources` is a list; `_write_sources`
  loops; chunk ids span all sources). The limiter is the **UI caller**.
- `litnav/ui/interactive.py::_build_open_world` feeds digest only `top = withft[0]` (the Architect's
  original cold-start design, commit 46a4978 — NOT introduced by our work). Live runs fetch ~3
  relevant sources and **discard 2**.
- Content per source is shallow by design: `fulltext.py::fetch_fulltext` → for arXiv,
  `corpus_expand._download_and_extract` reads only the **first 3 PDF pages**, `chunk_text(max_chunks=6)`
  → ~4KB (abstract+intro); non-arXiv = abstract only; Wikipedia = summary only. **Decision: leave the
  extractor depth as-is** (no page/chunk change) — fix breadth via multi-source + survey, not depth.
- `rank.py` + adapters have **no survey/review signal**; live searches surface 0 surveys even when
  famous ones exist. Ranking is relevance×citation-authority only.

## 3. Decisions (from brainstorming)
- Digest the **top 3** full-text sources (general-concepts backbone + up to 2 primary).
- **Soft, intent-aware survey boost** (never a hard filter; niche topics may have no survey).
- **Keep arXiv 3-page / 6-chunk extraction** unchanged (minimal-first; multi-source supplies breadth).
- **Upgrade Wikipedia to full-article** (44KB vs 103 chars) and use it as the general-concepts backbone
  for survey/crash-course/beginner goals (§4.4).

## 4. Components

### 4.1 Survey signal (`litnav/discover/contract.py` + `adapters/*`)
- Add `is_review: bool = False` to the `Source` dataclass (back-compatible default).
- Each adapter sets it: **title heuristic** (`survey`, `review`, `overview`, `tutorial`,
  `a comprehensive`) OR the API type when available — OpenAlex `work["type"] == "review"`; Semantic
  Scholar `publicationTypes` containing `"Review"`. OpenAlex/arXiv/Wikipedia/SE: title heuristic at
  minimum; OpenAlex + S2 also use the typed field.

### 4.2 Survey-priority rank boost (`litnav/discover/rank.py`)
- Extend the existing relevance(0.7)+authority(0.3) blend with an additive **survey bonus** when
  `source.is_review`, scaled by intent:
  - heavy (e.g. +0.20) for `survey` / `crash-course` / beginner-ish intents,
  - light (e.g. +0.05) for `cutting-edge`,
  - moderate default otherwise.
  (Exact weights are tunables surfaced as named constants.) Soft only — re-sorts, never filters.

### 4.3 Multi-source digest (`litnav/ui/interactive.py::_build_open_world`)
- Replace `[SourceDoc(top…)]` with the **top 3** of `withft` mapped to `SourceDoc`s:
  `withft[:3]`. `digest()` already ingests a list. The B/C streaming already shows N sources +
  concepts, so the richer build lights up for free. Route still teaches the first N concepts.

### 4.4 Wikipedia full-article backbone (`litnav/discover/adapters/wikipedia.py` + `fulltext.py`)
The Wikipedia adapter currently stores only the REST **summary** (`extract`) — for "Graph neural
network" that is **103 chars** (one sentence), so it contributes ~nothing to digest. Verified live: the
MediaWiki **extracts** endpoint (`action=query&prop=extracts&explaintext`, with the adapter's existing
User-Agent header) returns the **full article ≈ 44,701 chars** — a learner-altitude, jargon-free,
field-general overview whose sections ARE a concept map.
- Add full-article fetch to the Wikipedia source's full-text path (reuse the existing UA; non-fatal on
  failure, fall back to the summary). Chunk it with the existing `_chunk_text` (respect a per-source cap
  so the digest prompt stays bounded — e.g. the same `max_chunks` budget applied to the article body).
- **Prefer a Wikipedia article as the general-concepts BACKBONE for survey / crash-course / beginner
  goals** (alongside or ahead of a survey paper); for functional/mastery/cutting-edge goals it stays a
  normal candidate. This is the cleanest fix for the one-paper-jargon problem on beginner goals.
- Honest note: the 403 seen during research was a missing User-Agent in an ad-hoc test script, NOT an
  app bug — the adapter already sends a UA. Keep sending it.

### 4.5 Extraction nudge (`litnav/digest/extract.py`)
- One added line in the decompose prompt: prefer **general, field-level concepts a learner would
  recognize**, NOT one system's proprietary names/acronyms — so even a primary paper yields general
  concepts (the TME→TMT/TRIM failure mode).

## 5. Data flow
`find_sources` (adapters now tag `is_review`) → `rank` (survey-boosted, intent-aware) → top-k → fulltext
→ `_build_open_world` feeds **top-3** SourceDocs → `digest()` extracts field-general concepts across all
three → edges/verify/seeds → map. Streaming UI (B/C) shows the 3 sources + each concept.

## 6. Verification
- **Unit:** `is_review` detection (title + typed field) per adapter; `rank` boosts a review above an
  equally-relevant primary for a survey intent, and less so for cutting-edge; multi-source caller passes
  3 SourceDocs.
- **Adversarial DISCOVER battery** (live): on-topic rate ≥ current; surveys now surface for
  intro/survey goals.
- **Concept-plan sanity check** (live): the memory goal yields field-general concepts, not only one
  paper's jargon.
- **10-scenario live re-test**: target > 3.3; M4 (0 chunks/one paper) + narrow-plan complaints down.
- Offline suite green throughout.

## 7. Scope guard (YAGNI)
No digest re-architecture (already multi-source). No extractor depth change. No new pipeline stage.
Survey boost is additive to the existing rank blend. Top-N fixed at 3 (not adaptive-by-intent — deferred).

## 8. Risks
- More cost/latency on cold start (~3× extract) — accepted for plan quality; bounded by the unchanged
  3-page cap.
- Surveys can be stale/shallow — mitigated by the survey+primary mix and the soft (not hard) boost.
- Some topics have no survey — soft boost degrades gracefully to the current behavior.
