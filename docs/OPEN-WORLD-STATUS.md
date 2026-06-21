# Open-World LitNavigator — Status & Progress

**Branch:** `feat/open-world-digest` · **Updated:** 2026-06-21 · **Tests:** 272 passed

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
| `2026-06-21-ow0-5-e2e-evaluation.md` | **10-scenario live e2e evaluation** (real performance + ranked bugs); raw logs in `e2e-logs/` |
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
| **OW-4** — TEACH/ASSESS | ✅ done | ✅ `verify_teach_assess_live` | goal elicit → Bloom ceiling; metered grade with frontier **escalation**; MCQ distractors + flaw gate + weaker-simulator IRT; FSRS spacing + retention probe; teach-strategy policy + metacognitive reteach |
| **OW-5** — make-artifact | ✅ done | ✅ `verify_artifact_live` | scenario → format selector → mind-map / Cornell notes / Marp slides / worked-example / combination; every artifact carries a retrieval prompt + resolving citations; ~$0.0004/multi-format run |
| **OW-6** — recommend-next + dual frontend | ⏳ next | — | next-step ranker; Glass-box wired to `cost_ledger`; teacher override; progress streaming |
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

### OW-4 — TEACH/ASSESS ✅ (spec §6.3)
- **Code:** inner-loop LLM calls routed through the metered `router` (`assess_next`/`grade_kp`/`teach_kp`/`reteach_kp`); `litnav/nodes/goal_elicit.py` (goal_type → `bloom_ceiling`, graph entry); `grade_kp` **uncertainty escalation** (low-conf + near-threshold → frontier re-grade, the OW-0-deferred escalation gate / pedagogical-error-cost routing); `litnav/assess/quizgen.py` (distractors overgenerate-rank + SAQUET flaw gate + weaker-simulator `irt_b`); `litnav/assess/spacing.py` (FSRS-lite `review_queue` + `retention_log` predicted-vs-actual); `litnav/assess/strategy.py` (goal×expertise×KT policy) + metacognitive anti-over-help reteach.
- **Gate:** `verify_teach_assess` (offline determinism unit) + `verify_teach_assess_live` (LIVE capability).
- **Live result:** ALL PASS — goal classified live (`mastery`), 3 distractors pass the flaw gate, grade metered. Cost = goal-elicit $0.000043 + grade $0.000068 + quizgen $0.000039 = **$0.00015**. (No escalation fired — the answer was confidently correct + mastery below the band; escalation is selective by design.)
- **Deferred:** none new (escalation gate, deferred from OW-0, is now implemented here).

### OW-5 — make-artifact ✅ (spec §6.4)
- **Code:** `litnav/artifact/` — `contract.py` (`ArtifactInput`/`ArtifactResult`/`FORMATS`), `selector.py` (`select_format` §6.4 matrix: override→slides→worked_example→combination→mindmap→notes), `renderers/` (`mindmap.py` deterministic Mermaid from the concept graph; `notes.py` Cornell cues+summary, anti-verbatim; `slides.py` cheap-LLM JSON outline → deterministic Marp emitter; `worked_example.py` worked steps + one practice item), `make_artifact.py` (select → gather concepts/edges/evidence/citations from SQLite → render → write `<format>.md` → `ArtifactResult`; `combination` concatenates map+notes+worked into one file), `SKILL.md`.
- **Cross-cutting:** every renderer appends a **retrieval prompt** per segment + a **Citations** section; citations are real `paper_chunks.id` for the concepts (resolve 1:1).
- **Gate:** `verify_artifact` (offline unit: selector matrix, deterministic mind-map + combination, cross-cutting invariant) + `verify_artifact_live` (LIVE capability: notes/slides/worked rendered on real provider, citations resolve to real chunks, metered `stage='artifact'`).
- **Live result:** ALL PASS. Selector picks the right format for all 5 scenarios; notes are distilled (not verbatim), slides are valid Marp (front-matter + `---` + Citations slide), worked-example has grounded steps + practice Q&A. 4 cheap calls (notes 1 + slides outline 1 + worked 2 concepts) = **~$0.0004 / multi-format run** on `gpt-4o-mini`. Mind-map + combination run at **$0** (deterministic).
- **Live-surfaced fix:** `gpt-4o-mini` sometimes pre-numbers worked-example steps ("1. …", "Step 2 — …") → the deterministic emitter double-numbered ("1. 1. …"); now strips a leading enumerator before re-numbering (regression test added). *(This is exactly the kind of defect only a live run exposes — offline templates never pre-number.)*
- **Deferred (recorded):** Marp→`.pptx` is an external `marp-cli` post-step (we emit the `.md`), not a model; UI surfacing of artifacts → OW-6.

### OW-5.1 — persistence-chain repair ✅ (exposed by fresh-topic live e2e)
A fresh random topic (`diffusion models`, outside every fixture) run end-to-end LIVE revealed the digest→teach→artifact chain was **broken on real data while every gate was green** — because the gates asserted on in-memory returns / hand-seeded fixtures, never the persisted graph downstream stages consume.
- **Root causes & fixes:** (1) `create_concept` used `INSERT OR IGNORE`; an LLM `frontier_flag` outside the `CHECK` set silently dropped **every** concept → empty graph — now coerced to NULL (`repo.py`). (2) keypoint `evidence_chunk_id` (`'1','2'…`) never matched `cN` chunk ids — now normalized to a real chunk at write time (`pipeline.py`). (3) `make_artifact` read only `paper_chunks.concept_id` (NULL for digested data) → empty/uncited artifacts — now gathers via keypoint objectives + keypoint→chunk, with a **source-chunk pool fallback** so artifacts stay grounded + cited even when extraction yields no keypoints.
- **Gate hardening:** `verify_digest_live` now asserts concepts PERSIST + keypoint evidence resolves; **new `verify_openworld_e2e_live`** runs a fresh topic discover→digest→teach→artifact and asserts the persisted graph + non-empty grounded artifacts with resolving citations.
- **Live result (fresh `variational autoencoders`):** 7 concepts PERSISTED, keypoint evidence + quiz FKs valid, goal classified `mastery`, notes/slides/mindmap all non-empty + cited (resolve to real chunks). **~$0.003/run.**
- **Open findings (for the 10-scenario eval):** keypoint extraction is sparse/non-deterministic (sometimes 0); single-source full text isn't sub-chunked, so citations can collapse to `c0`; single-source digest yields 0 surviving prereq edges (richer/multi-source needed).

---

## Consolidated verification

**Offline gates (deterministic, $0):** `verify_m0` `verify_m1` `verify_m2` `verify_m3` `verify_cost` `verify_digest` `verify_discover` `verify_teach_assess` `verify_artifact` — all green. `pytest -q` = **272 passed**.

**LIVE gates (real provider, metered):**
| gate | result | cost |
|---|---|---|
| `verify_liveness` | ALL PASS | $0.000007 |
| `verify_cost_live` | ALL PASS (cap fires) | ~$0.00001 |
| `verify_digest_live` | ALL PASS (gpt-4o judge fires) | ~$0.0014 |
| `verify_discover_live` | ALL PASS (6 sources) | ~$0.0021 |
| `verify_teach_assess_live` | ALL PASS (goal/distractors/metered grade) | ~$0.00015 |
| `verify_artifact_live` | ALL PASS (notes/slides/worked live; citations resolve; metered stage=artifact) | ~$0.0004 |
| `verify_openworld_e2e_live` | ALL PASS (fresh topic discover→digest→teach→artifact; persisted graph; grounded cited artifacts) | ~$0.003 |

**Spec compliance:** OW-0..OW-3 fully aligned (research↔spec↔plan↔code↔tests); 7 prior deviations (RefD, query cache, papers.source_id, result cache, BM25, 80% alert, qwen bypass) all fixed; deferred items flagged inline in the spec. (Audit detail in `archive/`.)

## 10-scenario e2e evaluation (2026-06-21)
Full OW-0→5 live run over 10 diverse scenarios (goal/depth/prior/language/domain all varied). 9/10 ran
end-to-end; 1 aborted at discovery. **Detail:** [`2026-06-21-ow0-5-e2e-evaluation.md`](2026-06-21-ow0-5-e2e-evaluation.md).
Headline: the teaching machine (OW-2 persistence, OW-4, OW-5) is solid on good input and held up across
every language; **topical correctness is gated by DISCOVER source relevance (~44%; 0/4 non-English).**
Prioritized actions:
- **A5 (P0, OPEN → OW-3.1) — source-relevance gate:** relevance-filter the top source before digest; demote bare Wikipedia title hits (Raft→"Megalopolis", diffusion→physics).
- **A6 (P0, OPEN → OW-3.1) — non-English discovery:** normalize query to English for indices, teach in the user's language (es=0 sources, 中文=1 generic, fr=off-domain).
- **A7 (P1, ✅ CLOSED by PR #6)** — evidence-fed prereq judge: prereq survival 1/9 → **9/9** on the post-merge re-run.
- **A8 (P1, OPEN) — output-language control:** thread goal language into renderer/teach prompts (cues default to English on non-English concepts).
- **A9 (P2, OPEN) — sub-chunk full text:** citations still collapse to a single `c0`.
- **A10 (P2, ✅ CLOSED by PR #6)** — kp_id coercion + objective prompt: keypoints present 3/9 → **9/9**.
- **A11 (P1, OPEN, NEW) — digest cost ~5×** ($0.0034→$0.0169/run) from `digest_sim_judge` on frontier `gpt-4o`; evaluate moving the *similarity* judge to the cheap tier (keep the *prerequisite* judge on frontier).

**Post PR-#6 merge re-run (2026-06-21):** 9/10 full; **prereq 9/9, keypoints 9/9** (A7+A10 closed); concepts/artifacts grounded held; **A5/A6 unchanged → OW-3.1 next**; cost $0.0169/scenario (A11). Detail in the e2e evaluation doc.

## Action log (open)
- **A4** — multi-source digest live validation across many sources (code supports it; one multi-source run done). Candidate for OW-7.
- **Escalation gate / pedagogical-error-cost routing** — ✅ done in OW-4 (`grade_kp` frontier escalation near the mastery threshold).
- **Glass-box meter → cost_ledger; teacher override; progress streaming** — OW-6.
- **learner_goal slug↔ID reconciliation** — partially addressed by goal_elicit (OW-4); full reconciliation when the live cold-start path (OW-7) resolves slugs→ids.
- No model need recorded — `gpt-4o-mini` (extract/propose/**artifacts**) + `gpt-4o` (judge) + RefD are adequate; bottlenecks were code/prompt, not model tier. OW-5 confirms `gpt-4o-mini` produces well-grounded, concise, correctly-formatted notes/slides/worked-examples at ~$0.0004/run — no frontier tier needed for artifact generation.
