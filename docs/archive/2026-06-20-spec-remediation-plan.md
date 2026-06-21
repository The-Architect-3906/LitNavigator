# Spec-Remediation Plan — close all 7 unflagged deviations + re-align spec↔code

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Bring OW-0..OW-3 onto the spec: implement the 7 unflagged deviations (D1 RefD, D2 query cache, D3 papers.source_id, D4 §5 caching, D5 BM25 prefilter, D6 80% budget alert, D7 qwen bypass) and update the spec so intentional design choices + deferred items are recorded (no silent gaps). Live-verify and report.

**Architecture:** mostly additive — a RefD signal module + result-cache module + a BM25 prefilter + a generic `papers.source_id` + a discover query cache + cost-spine safety closes + spec doc edits. Live-first verification throughout.

**Tech Stack:** Python, existing `litnav.{llm,storage,digest,discover}`. Live gates per `docs/2026-06-20-live-gate-execution-contract.md`. Baseline: **213 passed**.

**Convention:** TDD offline per task; offline gates stay green; commit per task (no push; controller pushes). Live verification by controller at the end + the three-part report. Reference: `docs/2026-06-20-spec-compliance-audit.md`.

---

## Task 1 (D3): generic `papers.source_id`

**Files:** `litnav/storage/schema.py`, `litnav/storage/repo.py`, `litnav/digest/pipeline.py`; Test `tests/test_papers_source_id.py`.

Spec §4.1: `papers(source_type, source_id, url)`. Today only `arxiv_id` exists; non-arXiv sources misuse it.

- [ ] **Step 1: failing test** — after `create_paper(source_type="wikipedia", source_id="Software_agent", ...)`, a row exists with `source_id="Software_agent"` and `source_type="wikipedia"`; and digesting a wikipedia `SourceDoc` stores its `source_id` in `papers.source_id` (NOT arxiv_id).
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** schema migration: `ALTER TABLE papers ADD COLUMN source_id TEXT`. `repo.create_paper(conn, *, source_id=None, arxiv_id=None, title, source_type=None, url=None)` — write both columns (arxiv_id kept for back-compat; populate it only when source_type=='arxiv'). In `pipeline._write_sources`: `repo.create_paper(conn, source_id=s.source_id, arxiv_id=(s.source_id if s.source_type=="arxiv" else None), title=s.title, source_type=s.source_type, url=s.url)`.
- [ ] **Step 4:** run new test + `pytest -q` (expect 214) + verify_digest/verify_discover/verify_cost green. Report real.
- [ ] **Step 5: commit** `fix(spec-D3): generic papers.source_id (was arxiv_id-only)`.

---

## Task 2 (D2): reinstate the find-sources semantic query cache

**Files:** `litnav/discover/find_sources.py`; Test `tests/test_find_sources_cache.py`.

The OW-3 plan specced a `digest_cache`-backed query cache (`slice_key='discover:<hash>'`); the code dropped it. Reinstate as a demand-driven memoization keyed by (goal, intent, k).

- [ ] **Step 1: failing test** — two identical `find(...)` calls: the second is a cache hit (assert via a marker, e.g. `DiscoverResult` carries `cache_hit: bool` added to the contract, OR the adapters are monkeypatched and asserted called only ONCE across the two calls). Use the "adapters called once" form:
```python
def test_second_identical_find_skips_adapters(monkeypatch):
    calls = {"n": 0}
    def oa(q, k=10, fetch=None):
        calls["n"] += 1; return [Source("arxiv","x","u","T",0.9,abstract="a",arxiv_id="x")]
    monkeypatch.setenv("LITNAV_LLM_PROVIDER","none")
    monkeypatch.setattr(openalex,"search",oa); monkeypatch.setattr(wikipedia,"search",lambda *a,**k:[])
    monkeypatch.setattr(fulltext,"attach_fulltext",lambda s,*,top_k:None)
    c=sqlite3.connect(":memory:"); init_db(c)
    find_sources.find(DiscoverInput("goal",k=2),conn=c,session_id="s")
    find_sources.find(DiscoverInput("goal",k=2),conn=c,session_id="s")
    assert calls["n"] == 1   # second call served from cache, adapters not re-queried
```
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** add `cache_hit: bool = False` to `DiscoverResult` (contract.py). In `find_sources.find`: compute `key = "discover:" + sha1(f"{goal}|{intent}|{k}")[:16]`; on entry, `cache_get(conn, key)`; if cached, re-read the stored sources from a new `discover_cache` table OR (simpler) store the serialized `DiscoverResult` JSON in a small table `discover_results(key TEXT PRIMARY KEY, result_json TEXT)` and return it with `cache_hit=True`. Add `openworld_repo.discover_cache_get/put(conn, key, result_json)` + a `discover_results` table (schema migration). After a fresh discovery, store it. (Intent classify still runs before the cache key is known — that's fine; it's cheap. To avoid the intent LLM call on a hit, key on goal+k and classify only on miss.)
- [ ] **Step 4:** run + `pytest -q` (expect 215) + gates green. Report.
- [ ] **Step 5: commit** `fix(spec-D2): reinstate find-sources query cache (discover_results table)`.

---

## Task 3 (D5): BM25 keyword prefilter in ranking

**Files:** `litnav/discover/rank.py`; Test `tests/test_discover_bm25.py`.

Spec §6.1: "BM25 prefilter → SPECTER rerank". Add a lightweight BM25/keyword prefilter BEFORE the embedding-cosine rerank (which substitutes for SPECTER, already flagged). Pure-python BM25 over (title+abstract).

- [ ] **Step 1: failing test** — `rank.bm25_prefilter(goal, sources, keep)` returns at most `keep` sources, ordered by BM25 score vs the goal terms; a source with no goal-term overlap ranks below one with overlap.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** add `bm25_prefilter(goal_text, sources, keep)` to rank.py (pure-python Okapi BM25 over tokenized title+abstract; k1=1.5, b=0.75). In `rank_sources`, prefilter to `max(keep, 3*k)` BEFORE embedding (cheaper: fewer embeddings) then cosine-rerank the survivors. Offline (no embeddings) the BM25 order is a real keyword signal (better than authority-only). Keep dedup first.
- [ ] **Step 4:** run + `pytest -q` (expect 216) + gates. Report.
- [ ] **Step 5: commit** `fix(spec-D5): BM25 keyword prefilter before embedding rerank`.

---

## Task 4 (D6+D7): cost-spine safety — 80% budget alert + close qwen bypass

**Files:** `litnav/llm/router.py`, `litnav/llm/registry.py`, `litnav/llm/client.py`; Test add to `tests/test_router.py` (or test_llm_strict.py).

- [ ] **Step 1: failing tests:**
  - **D6:** after metering crosses 80% of `budget` (but below 100%), `router` records a `budget_alert` signal — implement as: `_meter` returns/logs when `spend >= 0.8*budget`; testable via a returned flag or a `cost_repo` row field. Simplest: `router._meter` appends to a module-level/threadlocal nothing; instead expose it on the call: add `alert_at_80` behavior by writing a `cost_ledger` row with `stage` suffixed? Too hacky. CLEANEST: add `litnav.llm.router.over_budget_fraction(conn, session_id, budget) -> float` helper AND have `_meter` emit a Python `warnings.warn(...)` once when crossing 80%. Test: assert `over_budget_fraction` ≥ 0.8 after enough spend, and that a warning fires (pytest.warns).
  - **D7:** `registry.resolve_tier` must govern the qwen path too: either add qwen models to MODEL_REGISTRY OR make `client._client()` for `provider=="qwen"` only resolve a model that the registry knows. Simplest faithful fix: a call with an unregistered model must be refused. Add a guard: `client.complete_*` asserts the resolved `actual` model is one the registry knows (collect allowed model names from `MODEL_REGISTRY`), else raise `LivenessError`/ValueError. Test: `provider=qwen` (model qwen-plus, not in registry) → router/client refuses (raises), not a silent call.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement:
  - D6: in `router._meter`, after recording, if `budget` and `0.8*budget <= spend < budget`, `warnings.warn(f"session {session_id} at {spend}/{budget} tokens (>=80%)", stacklevel=2)`. Add `over_budget_fraction(conn, session_id, budget)`.
  - D7: add a registry helper `enabled_model_names() -> set[str]` (the `model` values in MODEL_REGISTRY). In `client.complete_json/complete_text`, after computing `actual`, if `_provider() != "none"` and `actual` not in the enabled set AND no explicit per-call model override was passed by a non-router caller — raise. Careful: the router passes `model=spec["model"]` which IS enabled; the qwen path computes `"qwen-plus"` which is NOT enabled → refused. Keep `provider=none` unaffected. (Document: to enable qwen, add it to MODEL_REGISTRY.)
- [ ] **Step 4:** run + `verify_cost` (offline) green + `pytest -q` (expect 218). Report.
- [ ] **Step 5: commit** `fix(spec-D6,D7): budget 80% alert + refuse non-registry models (close qwen bypass)`.

---

## Task 5 (D4): semantic result cache (cosine≥0.92) + prompt-prefix note

**Files:** Create `litnav/llm/result_cache.py`; Modify `litnav/llm/router.py`, `litnav/storage/schema.py`; Test `tests/test_result_cache.py`.

Spec §5: "semantic result cache keyed by (stage, normalized_input_hash) with cosine≥0.92." Implement: exact-hash hit first (free); else embedding cosine≥0.92 within the same stage → return cached result; else miss. Opt-in per call (`cache=True`), enabled for digest stages.

- [ ] **Step 1: failing test** (offline-deterministic via a fake embedder injected):
```python
def test_exact_hash_hit_returns_cached(monkeypatch):
    # same (stage, prompt) -> second call returns cached result without calling the model again
    ...
def test_semantic_hit_above_092(monkeypatch):
    # a near-identical prompt whose injected embedding has cosine>=0.92 -> cache hit
    ...
def test_below_092_is_miss(monkeypatch):
    # cosine<0.92 -> miss (model called)
    ...
```
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** schema: `result_cache(stage TEXT, input_hash TEXT, embedding TEXT, result_json TEXT, created_at TEXT, PRIMARY KEY(stage,input_hash))`. `result_cache.py`:
  - `normalized_hash(prompt) = sha1(" ".join(prompt.split()).lower())[:16]`.
  - `lookup(conn, stage, prompt, *, embedder) -> (hit:bool, result|None)`: exact `(stage,input_hash)` → hit; else `embedder([prompt])` (one embed) and cosine vs stored embeddings for the stage, ≥0.92 → hit; else miss. (`embedder` defaults to `router.embed_texts` partial; injectable for tests.)
  - `store(conn, stage, prompt, result, *, embedder)`.
  - In `router.complete_json` add `cache: bool = False`: if cache, `lookup` first → on hit record a `cost_ledger` row with `cache_hit=True, total_tokens=0` (metered as cache hit) and return; else call, then `store`. Turn `cache=True` on in digest's extract/edge-propose/quiz-seed router calls (stage="digest") — NOT the judge (judging should be fresh).
- [ ] **Step 4:** run + `verify_cost`/`verify_digest` green + `pytest -q` (expect ~221). Report.
- [ ] **Step 5: commit** `fix(spec-D4): semantic result cache (exact-hash + cosine>=0.92), enabled for digest extract/propose`.

> Prompt-prefix caching: OpenAI applies automatic prefix caching for long stable prefixes server-side (no client code needed); note this in the cost-spine doc rather than implementing a client-side prefix cache.

---

## Task 6 (D1): RefD-style prerequisite signal + blend with the LLM

**Files:** Create `litnav/digest/refd.py`; Modify `litnav/digest/verify.py`, `litnav/digest/pipeline.py`; Test `tests/test_digest_refd.py`.

Spec §6.2: prereq edges = **"RefD-style + LLM"**. RefD (Liang 2015) = reference-distance asymmetry: B is a prerequisite of A if A's context references B more than B references A. Compute a corpus signal over the digest chunks and BLEND it with the LLM judge.

- [ ] **Step 1: failing test** `tests/test_digest_refd.py`:
```python
from litnav.digest import refd

def test_refd_directional_asymmetry():
    # concept B appears wherever A does, but A rarely appears where B does -> A depends on B
    concepts = [{"slug": "a", "name": "advanced topic"}, {"slug": "b", "name": "basic topic"}]
    # chunks: "basic topic" alone, and "advanced topic uses basic topic"
    by_chunk = {"c0": "basic topic explained", "c1": "advanced topic uses basic topic"}
    scores = refd.refd_scores(concepts, by_chunk)
    # prereq=b, target=a should be positive (a references b more than b references a)
    assert scores[("b", "a")] > 0
    assert scores[("a", "b")] <= 0

def test_refd_no_cooccurrence_is_zero():
    concepts = [{"slug": "a", "name": "alpha"}, {"slug": "b", "name": "beta"}]
    by_chunk = {"c0": "alpha only", "c1": "beta only"}
    scores = refd.refd_scores(concepts, by_chunk)
    assert scores[("a", "b")] == 0 and scores[("b", "a")] == 0
```
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** create `litnav/digest/refd.py`:
```python
"""RefD-style prerequisite signal (Liang et al. 2015), computed over the digest chunks.
B is a prerequisite of A when A's context references B more than B references A.
A non-LLM corpus signal that complements the LLM proposal/judge (spec §6.2 'RefD-style + LLM')."""
from __future__ import annotations
import re


def _terms(name: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", name.lower()) if len(w) > 3]


def _mentions(terms: list[str], text: str) -> bool:
    t = text.lower()
    return bool(terms) and any(term in t for term in terms)


def refd_scores(concepts: list[dict], by_chunk: dict) -> dict:
    """Return {(prereq_slug, target_slug): refd_score}. Positive => prereq_slug is a prerequisite
    of target_slug (target references prereq more than vice versa)."""
    chunks = list(by_chunk.values())
    terms = {c["slug"]: _terms(c.get("name", c["slug"])) for c in concepts}
    count = {s: sum(1 for ch in chunks if _mentions(terms[s], ch)) for s in terms}
    scores: dict = {}
    slugs = list(terms)
    for a in slugs:
        for b in slugs:
            if a == b:
                continue
            co = sum(1 for ch in chunks if _mentions(terms[a], ch) and _mentions(terms[b], ch))
            ref_a_to_b = co / count[a] if count[a] else 0.0     # of A's mentions, share also mention B
            ref_b_to_a = co / count[b] if count[b] else 0.0
            # refd for "prereq=b, target=a": A references B more than B references A => A needs B
            scores[(b, a)] = round(ref_a_to_b - ref_b_to_a, 4)
    return scores
```
- [ ] **Step 4:** blend into `verify.verify_pass`: accept an optional `refd: dict | None`. A high-impact prereq edge `(prereq, target)` is kept as `prerequisite` if `confidence >= VERIFY_THRESHOLD AND (judge agrees OR refd.get((prereq,target),0) >= REFD_MIN)` (REFD_MIN ~ 0.15). I.e. **RefD can corroborate an edge the judge alone would reject** (the two-signal design). Record which signal carried it (add `e["refd"] = score`). In `pipeline.digest`, compute `refd_scores(concepts, by_chunk)` and pass to `verify_pass`. Add a test that a judge-rejected edge with strong RefD survives as prerequisite.
- [ ] **Step 5:** run + `verify_digest` MUST stay green (the offline fixture: compute its refd over the 3-sentence chunks; if it changes the golden downgrade/accuracy, ADJUST the gate's expected values to the new two-signal result and document why — the golden is a determinism fixture, not capability truth). `pytest -q` report.
- [ ] **Step 6: commit** `feat(spec-D1): RefD-style prerequisite signal blended with the LLM judge (two-signal prereq)`.

---

## Task 7: re-align the spec doc (flag deferred + record intentional deviations)

**Files:** `docs/2026-06-20-open-world-architecture-spec.md`.

Make spec↔code one line (no silent gaps remaining):
- [ ] §5: add a "**Deferred to OW-4/OW-6**" note for the escalation gate + pedagogical-error-cost routing (OW-4) and the Glass-box meter wiring to `cost_ledger` (OW-6). Note prompt-prefix caching is server-side (OpenAI auto).
- [ ] §6.2: add "**Deferred**" notes for incremental graph extension (OW-4/7), user/teacher override (OW-6), UI progress streaming (OW-6). Note RefD is now implemented (Task 6).
- [ ] §4.1: add notes reconciling intentional design choices — embeddings stored in `chunk_vectors` (JSON) not an `embedding BLOB` column; IRT difficulty carried by `irt_b REAL` (legacy `difficulty` stays INTEGER); JSON columns named without the `_json` suffix (`evidence`, `held_misconceptions`, `tried_strategies`); `papers` now has generic `source_id` (Task 1).
- [ ] §6.1: note BM25 prefilter now implemented (Task 3); query cache reinstated (Task 2); SPECTER→embedding-cosine, S2/youtube/iterative-rounds remain recorded-deferred.
- [ ] Cross-link `docs/2026-06-20-spec-compliance-audit.md` from §10/§13.
- [ ] **Commit** `docs(spec): re-align spec with code — flag deferred items + record intentional deviations`.

---

## Controller live verification → three-part report (NOT a subagent task)
After Tasks 1–7 land, the controller runs LIVE (real provider + network):
```bash
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_digest_live      # RefD + cache in digest
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_discover_live     # BM25 + query cache + source_id
```
Plus a focused multi-source digest probe (feed find-sources' top sources into one digest) to show RefD + two-signal prereqs on real full text. Produce the three-part report (live usage + cost table — show the result-cache hits → $0 rows — + evaluation: did RefD recover real prerequisites? optimize? action points?). Then a final spec-compliance re-check: all 7 D-items resolved, deferred items now flagged.

## Self-Review
- D1 RefD (T6), D2 query cache (T2), D3 source_id (T1), D4 result cache (T5), D5 BM25 (T3), D6 80% alert + D7 qwen (T4), spec re-alignment (T7). All 7 + flagging covered. ✓
- Live-first: live verification + report at the end; offline gates stay green per task. ✓
- No new ENABLED model (RefD is non-LLM; caches use the embed tier; qwen is now *refused* unless registered). ✓
- Type consistency: `create_paper(source_id=...)`, `refd_scores`, `result_cache.lookup/store`, `bm25_prefilter`, `over_budget_fraction`, `DiscoverResult.cache_hit` used consistently. ✓
