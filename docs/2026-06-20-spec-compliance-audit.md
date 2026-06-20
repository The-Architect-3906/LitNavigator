# Spec-Compliance Audit — OW-0 … OW-3 (+ live fixes)

**Date:** 2026-06-20 · **Method:** 4 parallel read-only audits (one per milestone) vs `docs/2026-06-20-open-world-architecture-spec.md`. Classification: ✓ matches · ⚠ testing-gap (code supports, not validated) · ✗ unflagged deviation · ◻ deferred.

> Note: the live-first re-audit **intentionally superseded §10** (offline gates → live gates). That is by design and NOT counted as a deviation here. This audit checks the CAPABILITY/data specs (§4, §5, §6.1, §6.2).

**Bottom line:** the core architecture and data-flow follow the spec faithfully across all four milestones. But the audit found **~7 genuine unflagged deviations** (built differently or omitted without recording it) plus several legitimately-deferred-but-unflagged items and cosmetic naming diffs. My earlier "core faithful, only RefD missing" was **incomplete** — there are more.

---

## ✗ Genuine UNFLAGGED deviations (built differently / omitted, not recorded anywhere)

| # | Spec | What spec says | What we built | Severity |
|---|---|---|---|---|
| D1 | §6.2 | prereq edges = **"RefD-style + LLM"** | **LLM-only** proposal; RefD (corpus reference-distance signal) entirely absent | **High** — RefD is a non-LLM prereq signal; its absence is directly tied to "all prereqs get LLM-downgraded" |
| D2 | §6.1 | **Semantic query cache** (the OW-3 plan itself specced `_query_key` + cache) | `find_sources.py` has **no cache** — silently dropped from the plan's own design | **Med** — process miss (plan had it, code didn't); re-discovery re-bills every time |
| D3 | §4.1 | `papers(... source_id ...)` generic id | only `arxiv_id TEXT UNIQUE`; non-arXiv sources' ids get shoved into `arxiv_id` | **Med** — breaks clean multi-source provenance |
| D4 | §5 | **Caching**: prompt-prefix cache + semantic result cache (cosine≥0.92) | neither implemented; `digest_cache` is coarse slice memoization; `cache_hit` hardcoded False | **Med** — a cost lever the spec wanted, unbuilt + unassigned |
| D5 | §6.1 | **BM25 prefilter** before rerank | not implemented (embedding-cosine only); SPECTER was flagged-deferred but BM25 was not | **Low** |
| D6 | §5 | budget **"alert at 80%"** | only the hard cap fires; no 80% warning | **Low** |
| D7 | §5 | model-need protocol: never call a non-enabled model | `LITNAV_LLM_PROVIDER=qwen` routes to `qwen-plus` (not in `MODEL_REGISTRY`) — a silent bypass | **Low-Med** (safety) — legacy provider hole vs the "never enable silently" rule |

## ◻ Deferred but NOT explicitly flagged (legitimately later milestone — should have been recorded as deferred)

| Spec | Item | Proper home |
|---|---|---|
| §5 | Escalation gate + pedagogical-error-cost routing + reason logging | OW-4 (teach/assess) |
| §6.2 | Incremental graph extension ("extend as learner strays") | OW-4 / OW-7 |
| §6.2 | user/teacher edge override | OW-6 (frontend) |
| §6.2 / §5 | stream digest progress to UI; Glass-box meter wired to `cost_ledger` (currently `ui/cost.py` reads the old `tutor_turns`) | OW-6 (dual frontend) |
| §6.1 | 2–3 iterative rounds for systematic intent | recorded in OW-3 plan/SKILL ✓ (flagged) |

## ◻ Flagged-deferred (properly recorded — acceptable)
S2 + youtube-transcript adapters; SPECTER rerank (→ embedding cosine); 2–3 iterative rounds; multi-source live validation (A4); hard prereq-survival floor (→ OW-3/full-text); live quiz-seed (A-quiz). All in eval-log / OW-3 plan / SKILL.md.

## Cosmetic / low-priority (functionally equivalent)
- Column naming: `evidence` vs spec `evidence_json`; `held_misconceptions`/`tried_strategies` vs `*_json`. (Columns exist, hold JSON.)
- `quiz_items.difficulty INTEGER` vs spec `REAL` — but `irt_b REAL` carries the IRT difficulty, so functionally covered.
- `paper_chunks` embedding lives in a separate `chunk_vectors` table (JSON) vs spec's `embedding BLOB` column — pre-existing M4 design choice, functionally equivalent.
- `Source.source_id` vs spec output key `id`; arXiv surfaced via OpenAlex ids (no standalone arXiv search) — narrower but full-text is fetched.

---

## ✓ What faithfully matches spec (the core)
- **OW-0 §5:** model-need protocol (only cheap/frontier enabled; others record-only; `resolve_tier` raises) ✓; metering writes `cost_ledger` on every call ✓; per-session hard budget cap (live-proven) ✓; digest_cache self-warms from real requests, no allowlist ✓.
- **OW-1 §4:** all of §4.2 (learner_state.irt_theta, learner_goal, review_queue) and §4.3 (digest_cache, cost_ledger) present + correct; concepts.source/domain, concept_edges.similarity+source+confidence, keypoints.bloom_level, quiz_items.distractors_json/irt_b, papers.source_type/url all present.
- **OW-2 §6.2:** sources plural (multi-source code path) ✓; full output shape ✓; cheap-extract → similarity+prereq → frontier-verify-high-impact-only → confidence → write digested + flag low-conf ✓; edge-accuracy spot-check ✓; sliced (target_slugs) ✓; KnowLP similarity fallback ✓; result cache ✓.
- **OW-3 §6.1:** input/output shape ✓; intent classifier ✓; OpenAlex + Wikipedia adapters ✓; dedup ✓; authority score ✓; metadata-first + top-k full-text ✓.

---

## Recommended remediation (priority order)
1. **D1 RefD** — add the corpus reference-distance prereq signal (spec's "RefD-style + LLM"); most substantive + tied to prereq quality.
2. **D3 papers.source_id** + **D2 query cache** — multi-source correctness + the cache the OW-3 plan already specced.
3. **D7 qwen bypass** + **D6 80% alert** — cheap safety/metering closes.
4. **D4 caches / D5 BM25** — cost/quality levers; can fold into a cost-refinement pass.
5. **Explicitly flag** the deferred §5/§6.2 items (escalation, incremental, override, UI-stream, Glass-box wiring) as OW-4/OW-6 in the spec so they stop reading as silent gaps.
6. Cosmetic naming — optional cleanup.
