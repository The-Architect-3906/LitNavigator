# Open-World LitNavigator — Status & Progress

**Branch:** `feat/open-world-digest` · **Updated:** 2026-06-20 · **Tests:** 231 passed (56 files)

This is the single source of truth for *where the open-world build is*. It is organized by the
architecture spec's milestones (§9). Detailed execution records, the live-first re-audit, the
spec-compliance audit, and the per-cycle eval log are archived under `docs/archive/`.

## Document map
| Doc | Role |
|---|---|
| `2026-06-20-open-world-research-brief.md` | Research questions + design rationale (source) |
| `2026-06-20-open-world-literature-review.md` | Verified literature + evidence grades + risk flags |
| `2026-06-20-open-world-architecture-spec.md` | **Full architecture spec — source of truth** (impl-notes + deferred flags inline) |
| `2026-06-20-live-gate-execution-contract.md` | How LIVE gates run (provider, budget, liveness, outage) |
| **this file** | Per-module status / done / not-done / live results |
| `archive/` | Per-milestone plans, audits, re-audit, per-cycle eval log |

## Doctrine (live-first)
The open-world capability is validated **LIVE on real input** — offline gates exist only for
deterministic safety/math (formulas, schema, budget cap, cache logic). A green offline run is **not**
evidence a capability works; each capability skill has a `verify_*_live` gate. Every LLM/embedding call
is metered through one router chokepoint; a strict mode makes a real call **distinguishable from a
silent fallback** (a dead provider raises, never silently returns a fixture).

---

## Milestone status

| Milestone | Status | Live-verified | One-line |
|---|---|---|---|
| **Phase 0** — LLM liveness precondition | ✅ done | ✅ `verify_liveness` | strict mode + `was_live()`; a real call is provably distinct from a fallback |
| **OW-0** — Cost spine | ✅ done | ✅ `verify_cost_live` | metered router, registry, per-session budget cap (fires on real spend), result cache, 80% alert |
| **OW-1** — Data model | ✅ done | ✅ (via digest) | concept-graph + learner + cache + ledger schema; repo writers |
| **OW-2** — digest-corpus | ✅ done | ✅ `verify_digest_live` | sources → 8 concepts → RefD+LLM edges → gpt-4o judge → digested graph; deterministic; ~$0.003/run |
| **OW-3** — find-sources | ✅ done | ✅ `verify_discover_live` | intent → OpenAlex+Wikipedia → BM25+rerank+dedup+authority → top-k full text; ~$0.0001/run |
| **OW-4** — TEACH/ASSESS | ⏳ next | — | goal elicitation, Bloom quiz, distractors, IRT difficulty, uncertainty grading, FSRS, retention probe, escalation gate |
| **OW-5** — make-artifact | ⏳ pending | — | mind-map / notes / slides / worked-example, scenario-selected format |
| **OW-6** — recommend-next + dual frontend | ⏳ pending | — | next-step ranker; Glass-box wired to `cost_ledger`; teacher override; progress streaming |
| **OW-7** — live cold-start | ⏳ pending | partial | end-to-end real-topic digest→teach (digest path already live); streamed progress + demo cache pre-fill |

---

## Per-module detail

### Phase 0 — liveness precondition ✅
- **Code:** `litnav/llm/client.py` (`LivenessError`, `was_live()`, `LITNAV_LLM_STRICT`).
- **Gate:** `verify_liveness` (LIVE) — real call registers live (tokens>0); a forced provider error **raises** in strict mode (not a silent fallback). Offline → SKIP.
- **Live result:** ALL PASS. Real "pong" call = 18 tokens / $0.000007; forced connection error raises.

### OW-0 — Cost spine ✅ (spec §5)
- **Code:** `llm/registry.py` (enabled: `cheap`=gpt-4o-mini, `frontier`=gpt-4o, `embed`=text-embedding-3-small; record-only: mid/reranker/tutor-dpo-small), `llm/router.py` (single metered chokepoint, tier routing, budget cap + 80% alert, refuses non-registry models), `storage/cost_repo.py` + `cost_ledger`, `llm/result_cache.py` (exact-hash + cosine≥0.92).
- **Gate:** `verify_cost_live` (LIVE) — real spend metered (tokens>0, usd>0), embed metered, **budget cap fires on real accumulating spend**. Offline `verify_cost` (math/refusal).
- **Live result:** ALL PASS.
- **Deferred:** escalation gate + pedagogical-error-cost routing → **OW-4**; Glass-box live meter wired to `cost_ledger` → **OW-6** (currently `ui/cost.py` reads legacy `tutor_turns`).

### OW-1 — Data model ✅ (spec §4)
- **Code:** `storage/schema.py` (concepts `source`/`domain`/`slice_key`; concept_edges `similarity`+`source`+`confidence`+`slice_key`; keypoints `bloom_level`; quiz_items `distractors_json`/`irt_b`; papers `source_type`/`url`/`source_id`; learner_state `irt_theta`; new tables `learner_goal`, `review_queue`, `digest_cache`+`model_key`, `cost_ledger`, `result_cache`, `discover_results`; `paper_chunks`), `storage/repo.py` + `storage/openworld_repo.py` writers.
- **Tested:** `test_ow1_schema`, `test_digest_repo`, `test_papers_source_id`, `test_openworld_repo`.
- **Impl note (vs spec §4.1):** embeddings live in `chunk_vectors` (JSON), not an `embedding BLOB` column; IRT difficulty in `irt_b REAL` (legacy `difficulty` stays INTEGER); JSON columns un-suffixed (`evidence`, etc.).
- **Deferred:** `learner_goal` slug↔ID reconciliation → **OW-4**.

### OW-2 — digest-corpus ✅ (spec §6.2)
- **Code:** `litnav/digest/` — `extract.py` (granular concepts, temp=0, cheap tier, cache), `edges.py` (`_propose_edges` LLM over extracted slugs + similarity cosine + evidence cleaning), `refd.py` (RefD reference-distance prereq signal), `verify.py` (`verify_pass`: single frontier judge + **RefD-or-judge** keeps a prereq + downgrade + edge-accuracy), `pipeline.py` (orchestrate → write `source='digested'` → slice cache).
- **Gate:** `verify_digest_live` (LIVE capability) — concepts>0, edges over extracted slugs, evidence resolves, judge ran on **real gpt-4o**, graceful downgrade. Offline `verify_digest` = determinism/schema unit test (golden fixture, NOT capability evidence).
- **Live result:** ALL PASS. Multi-source (3 real sources) → 8 concepts, edges built; **RefD recovered a real prerequisite** (`in_context_learning → agentic_reasoning`) the LLM judge alone rejected — the "RefD-style + LLM" two-signal design working. ~$0.003/digest.
- **Deferred:** incremental graph extension → **OW-4/7**; user/teacher edge override + UI progress streaming → **OW-6**.

### OW-3 — find-sources ✅ (spec §6.1)
- **Code:** `litnav/discover/` — `intent.py` (cheap classifier + heuristic), `adapters/openalex.py` (discovery + citation authority), `adapters/wikipedia.py` (background), `rank.py` (BM25 prefilter → embedding-cosine rerank + authority + dedup), `fulltext.py` (arXiv PDF reuse for top-k), `find_sources.py` (orchestrator + query cache).
- **Gate:** `verify_discover_live` (LIVE) — real OpenAlex/Wikipedia + arXiv full text; feeds a source into digest. Offline `verify_discover` (parsing/rank/dedup/intent).
- **Live result:** ALL PASS. 6 real sources with authority, intent classified, top-k full text. ~$0.0001/discover.
- **Deferred (recorded):** Semantic Scholar + youtube-transcript adapters; standalone arXiv search; SPECTER rerank (→ embedding cosine); 2–3 iterative rounds for systematic intent.

---

## Consolidated verification

**Offline gates (deterministic, $0):** `verify_m0` `verify_m1` `verify_m2` `verify_m3` `verify_cost` `verify_digest` `verify_discover` — all green. `pytest -q` = **231 passed**.

**LIVE gates (real provider, metered):**
| gate | result | cost |
|---|---|---|
| `verify_liveness` | ALL PASS | $0.000007 |
| `verify_cost_live` | ALL PASS (cap fires) | ~$0.00001 |
| `verify_digest_live` | ALL PASS (gpt-4o judge fires) | ~$0.0014 |
| `verify_discover_live` | ALL PASS (6 sources) | ~$0.0021 |

**Spec compliance:** OW-0..OW-3 fully aligned (research↔spec↔plan↔code↔tests); 7 prior deviations (RefD, query cache, papers.source_id, result cache, BM25, 80% alert, qwen bypass) all fixed; deferred items flagged inline in the spec. (Audit detail in `archive/`.)

## Action log (open)
- **A4** — multi-source digest live validation across many sources (code supports it; one multi-source run done). Candidate for OW-7.
- **Escalation gate / pedagogical-error-cost routing** — OW-4.
- **Glass-box meter → cost_ledger; teacher override; progress streaming** — OW-6.
- No model need recorded — `gpt-4o-mini` (extract/propose) + `gpt-4o` (judge) + RefD are adequate; bottlenecks were code/prompt, not model tier.
