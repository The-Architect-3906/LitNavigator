# Open-World LitNavigator — Architecture Spec

**Date:** 2026-06-20 · **Branch:** `feat/open-world-digest`
**Source of truth for design rationale:** [research brief](2026-06-20-open-world-research-brief.md)
+ [literature review](2026-06-20-open-world-literature-review.md) (evidence grades + risk flags)

> **For agentic workers:** this is the umbrella architecture. Each numbered skill/subsystem in §6
> becomes its own implementation plan (sub-project) via `superpowers:writing-plans`. Do not
> implement from this doc directly.

---

## 1. Goal & scope

Turn LitNavigator from a **bounded, curated tutor** (what `main` ships) into an **open-domain
tutor**: given any learning goal, it finds the most suitable sources, digests them into a teachable
concept graph, teaches adaptively in multiple formats, assesses with calibrated quizzes, and
recommends what to learn next — all under strict cost control.

**In scope:** live source discovery, live digest, multi-format teaching output, redesigned
assessment, next-step recommendation, dual frontend, cost governance.
**Out of scope (this branch, for now):** training/fine-tuning our own models (record as needs only),
mobile, multi-user accounts, offline-only operation (the demo pre-warms domains, but the system
assumes a provider is available).

**Reuse from `main` (do not rebuild):** LangGraph `StateGraph` + `SqliteSaver`; the keypoint
TEACH/ASSESS inner loop (`teach_kp`/`assess_next`/`grade_kp`/`reteach_kp`); `concept_graph()` +
`graph_svg`; the semantic-grading seam; `litnav/llm/client.py` provider abstraction; `ui/cost.py`;
the two-pane Chat / Glass-box UI.

## 2. Principles (non-negotiable)

1. **Grounded, not open-ended bluffing.** Teaching content is always cited to retrieved evidence.
   Open-domain ≠ ungrounded — it means we *go fetch and digest* a source, then teach from it.
2. **The learner model is BKT/Rasch, never LLM self-assessment** (2603.02830; 2605.16207).
3. **Cost is a first-class architectural constraint**, designed in via a three-tier model cascade,
   caching, and precompute — not bolted on. Every external/LLM call is metered.
4. **Concept graph is the spine.** Every stage reads/writes it. Edges are typed:
   `prerequisite` *and* `similarity` (KnowLP/2506.22303 — similarity is the fallback when a prereq
   chain blocks the learner).
5. **Determinism where it matters.** The teach/assess inner loop stays a reproducible LangGraph
   state machine; only the open-ended outer stages are free-form agent calls.
6. **Two surfaces, one engine.** Product Chat (clean) and Glass-box (full technical chain) render
   the same state.

## 3. High-level architecture

```
                 ┌──────────────────────────────────────────────────────────┐
   user goal ───▶│  OUTER AGENT LOOP  (ReAct + Plan-and-Solve front pass)    │
                 │  decides which STAGE SKILL to invoke, in order, per state │
                 └───┬───────────────┬───────────────┬───────────────┬───────┘
                     │               │               │               │
              ┌──────▼──────┐ ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼───────┐
   SKILLS:    │ find-sources│ │ digest-     │  │ make-      │  │ recommend-  │
   (SKILL.md) │ (DISCOVER)  │ │ corpus      │  │ artifact   │  │ next        │
              └──────┬──────┘ │ (DIGEST)    │  │ notes/map/ │  └─────┬───────┘
                     │        └──────┬──────┘  │ slides     │        │
              ┌──────▼──────┐        │         └─────┬──────┘        │
   TOOLS/MCP: │ OpenAlex /  │        │               │              │
              │ S2 / arXiv /│        ▼               │              │
              │ Wikipedia / │   writes to            │              │
              │ yt-transcript│  CONCEPT GRAPH ◀──────┴──────────────┘
              └─────────────┘        │
                                     ▼
                 ┌──────────────────────────────────────────────────────────┐
   LANGGRAPH     │  INNER LOOP (deterministic, checkpointed) — reuse main:   │
   SPINE:        │  orient → teach_kp → assess_next → grade_kp → route       │
                 │  reads learner model + concept graph; never self-assesses │
                 └──────────────────────────────────────────────────────────┘

   STORES: concept-graph DB · learner model (BKT/Rasch) · digest cache (warm/cold)
           · cost ledger · FSRS review queue
   COST:   model-router tier on every LLM call · prompt+semantic cache · metering
```

## 4. Data model

Extends `main`'s schema (additive; existing tables keep working).

### 4.1 Concept graph
- `concepts(id, slug, name, domain, frontier_flag, source ∈ {curated, digested, induced})`
- `concept_edges(prereq_concept, target_concept, edge_type ∈ {prerequisite, similarity},
  source ∈ {curated, digested, induced}, confidence REAL, evidence_json)` — **new: `similarity`
  edge_type** (KnowLP fallback).
- `keypoints(id, concept_id, name, objective, evidence_chunk_id, sort_order, bloom_level)`
- `quiz_items(id, concept_id, keypoint_id, bloom_level, qtype, question, answer_key, rubric,
  distractors_json, difficulty REAL, irt_b REAL NULL, evidence_chunk_id)` — **new: `distractors_json`,
  `difficulty`, `irt_b`.**
- `paper_chunks(id, paper_id, concept_id, section, text, embedding BLOB NULL)`
- `papers(id, source_type ∈ {arxiv, wikipedia, youtube, pdf, web}, source_id, title, url)` —
  **new: `source_type`, `url`.**

> **Impl note (2026-06-20):** Several intentional deviations exist between the schema above and the
> code as built through OW-3 — all functionally equivalent or improvements, recorded here:
>
> - **Embeddings storage:** chunk embeddings live in a separate `chunk_vectors` table (JSON vector
>   column), NOT as an `embedding BLOB` column on `paper_chunks`. This is the pre-existing M4 design
>   choice; it separates large vector data from chunk metadata (functionally equivalent).
> - **IRT difficulty:** `quiz_items.irt_b REAL` carries the Rasch IRT difficulty parameter as
>   specced; the legacy `quiz_items.difficulty` column remains as `INTEGER` (not changed to `REAL`).
>   For all IRT computations `irt_b` is authoritative.
> - **JSON column naming:** the JSON-holding columns in the live schema omit the `_json` suffix:
>   `concept_edges.evidence` (not `evidence_json`), `learner_state.held_misconceptions` (not
>   `held_misconceptions_json`), `learner_state.tried_strategies` (not `tried_strategies_json`).
>   They hold JSON; the naming is cosmetic.
> - **`papers.source_id`:** the live schema has only `arxiv_id TEXT UNIQUE`; non-arXiv source ids
>   were written into `arxiv_id`. A generic `source_id` column is being added as part of this
>   remediation (closes audit finding D3) — the spec entry above already reflects the target state.

### 4.2 Learner model (the ground truth)
- `learner_state(session_id, concept_id, mastery REAL, confidence REAL, n_observations,
  held_misconceptions_json, tried_strategies_json, irt_theta REAL NULL)` — extend with Rasch/IRT
  ability `irt_theta`.
- `learner_goal(session_id, goal_text, goal_type ∈ {mastery, functional, survey}, target_concepts_json,
  created_at)` — **new (goal elicitation).**
- `review_queue(session_id, concept_id, due_at, fsrs_state_json)` — **new (FSRS spacing).**

### 4.3 Digest cache & cost
- `digest_cache(slice_key, status ∈ {cached, building}, graph_version, built_at,
  human_checked BOOL)` — **the default is live digest on demand (every slice is "cold").** This
  table is a **pure results cache (memoization)**: a slice already digested once is not re-digested
  — an optimization, not a prediction, and required by the minimal-spend rule. It only ever remembers
  *real past requests*; there is **no pre-picked "warm domain" allowlist** (that would be
  unrealistic). The system works with an empty cache (just slower/costlier). (The demo merely
  pre-runs the digest for the topic it will show, to fill that one cache entry — a staging
  convenience, not a product assumption.)
- `cost_ledger(session_id, ts, stage, tier, model, total_tokens, usd, cache_hit)` —
  **new; backs the live cost meter and per-session budget cap.** (OW-0 records `total_tokens` ×
  a blended per-tier rate; an input/output token split is a later refinement.)

## 5. The model router & cost governance (build this FIRST — everything depends on it)

A single chokepoint: `litnav/llm/router.py` wraps `llm/client.py`.

- **Three tiers**, declared in a registry (`MODEL_REGISTRY`): `cheap` (default `gpt-4o-mini`),
  `mid` (reserved; record-only until approved), `frontier` (default `gpt-4o`, cold-start
  explanation + flagged escalations only). Routing decisions that are *not* generative (mastery
  update, item selection) never call an LLM.
- **Escalation gate:** start at `cheap`; escalate to `frontier` only on an explicit signal
  (cold-start concept explanation; low grader confidence; user-facing teaching for a Mastery-goal
  learner). Logged with reason. **Escalation is priced against PEDAGOGICAL-error cost, not token
  cost** (lit-review): a wrong correctness judgment near a mastery threshold is costly, so escalate
  there even though tokens are cheap — token-cost-only routing (FrugalGPT/RouteLLM defaults) is the
  wrong objective for a tutor.
- **Caching:** prompt caching on stable prefixes (learner profile, SKILL.md body, digest);
  semantic result cache keyed by `(stage, normalized_input_hash)` with cosine≥0.92.
- **Precompute:** the `digest_cache` self-warms from real requests (§4.3); no domain is precomputed
  by prediction. The demo may pre-fill one cache entry for its shown topic (staging convenience).
- **Metering & budget:** every call writes `cost_ledger`; a per-session `token_budget` hard-caps
  spend; alert at 80%; tool-loop caps prevent runaway. Glass-box shows the live meter.
- **Model-need protocol:** the only ENABLED models are today's (`gpt-4o-mini` cheap, `gpt-4o`
  frontier). **Any** other need or better option — **including non-OpenAI providers** (Anthropic,
  open-weights, a DPO-tuned tutor model, a reranker, etc.) — is added to `MODEL_REGISTRY` as
  `record-only` (disabled) with a one-line rationale and surfaced for approval. **Never enable a new
  model silently.**

> **Deferred → OW-4:** The escalation gate (start-cheap → frontier-on-signal), reason-logging per
> escalation decision, and pedagogical-error-cost routing are implemented at OW-4 (teach/assess
> extensions). OW-0 ships the metered chokepoint, `MODEL_REGISTRY`, per-session budget hard cap,
> and (now, as of this remediation) the 80% spend alert + a hard refusal of any model not present
> in `MODEL_REGISTRY` (closes audit finding D7 — the qwen-plus silent bypass).
>
> **Impl note (2026-06-20):** The semantic result cache (exact hash + cosine ≥ 0.92) is
> implemented in `litnav/llm/result_cache.py` and is enabled for digest structured calls (closes
> audit finding D4 for the result-cache half). Prompt-prefix caching is handled server-side by
> OpenAI's automatic prefix cache — no client-side code is required or maintained.
>
> **Deferred → OW-6:** The Glass-box live meter is not yet wired to `cost_ledger`. The current
> `ui/cost.py` reads the legacy `tutor_turns` table; rewiring to `cost_ledger` is part of the
> dual-frontend milestone (OW-6).

## 6. Stage skills — contracts

Each is an Anthropic Skill (`SKILL.md` + scripts) the outer agent invokes. Contracts are JSON;
each must run offline-deterministically when `provider=none` (return a fixture or a clear error).

### 6.1 `find-sources` (DISCOVER)
- **In:** `{goal_text, intent ∈ {crash-course, systematic, applied, reference, cutting-edge},
  budget}`
- **Out:** `{sources: [{source_type, id, url, title, authority_score, why}], intent_used}`
- **How:** **query normalization (any-language goal → English search query)** → intent classifier →
  source-type stack → tool calls (OpenAlex/S2/arXiv/Wikipedia/youtube-transcript) → BM25 prefilter →
  SPECTER rerank → dedup → authority score → **relevance gate (cheap LLM drops off-topic sources)**.
  2–3 iterative rounds for systematic/deep intents.
- **Cost:** metadata-only first; full-text fetch only top-k. Semantic query cache.

> **Impl note (2026-06-20):** BM25 keyword prefilter and the semantic query cache are now
> implemented (closes audit findings D2 and D5). SPECTER rerank is substituted by
> `text-embedding-3-small` cosine similarity (SPECTER deferred — recorded in OW-3 plan/SKILL.md).
> Adapters shipped: **OpenAlex** + **Wikipedia** (plus arXiv full-text fetch for top-k results via
> OpenAlex ids). arXiv is currently reached through OpenAlex ids; there is no standalone arXiv
> *search* adapter.
>
> **Impl note (2026-06-21, OW-3.1):** Two cheap-LLM seams were added after a 10-scenario live e2e
> found source relevance ~44% and non-English discovery 0/4. (1) `discover/query.py::to_search_query`
> normalizes any-language goals to an English search query for the English-biased adapters + cosine
> rerank; (2) `discover/relevance.py::relevance_gate` drops sources not actually about the topic
> (a film/different-field page) AFTER ranking, BEFORE full-text fetch, never starving digest (keeps
> ≥ min_keep by rank). Both pass through deterministically at `provider=none`. The user's original
> `goal_text` is preserved for intent + downstream teaching language; **output-language localization of
> teaching/artifacts (A8) remains a recorded follow-up.**
>
> **Deferred (recorded):** Semantic Scholar + youtube-transcript adapters; a standalone arXiv
> search adapter; 2–3 iterative rounds for systematic intent (recorded in OW-3 plan as A-iter);
> multi-source digest (A7 is closed for prereq survival via the evidence-fed judge, but top-k digest
> for breadth is still recorded); output-language localization (A8).

### 6.2 `digest-corpus` (DIGEST)
- **In:** `{sources, domain_key}`
- **Out:** `{concepts[], edges[(prereq|similarity), confidence, evidence], keypoints[], quiz_seeds[],
  unverified_edges[]}`
- **How:** chunk+embed → concept/keyphrase extraction (cheap model) → **prereq edges (RefD-style +
  LLM) AND similarity edges** → keypoint+evidence binding + Bloom tag → **verify pass (frontier
  model) on high-impact edges only** → confidence scores. Writes to concept graph; low-confidence
  edges flagged, not silently trusted.
- **Edge-accuracy spot-check (lit-review risk A).** Prerequisite-edge accuracy is the field's
  dominant bottleneck and is **untested when the graph is built live from open-web sources** — likely
  worse than the closed-corpus benchmarks. So `digest-corpus` emits an **edge-accuracy sample
  metric**: sample N new edges, score each by independent LLM-judge (and optional human) agreement,
  and surface that number in the Glass-box. Below a threshold → keep edges as `similarity` / flagged,
  not hard `prerequisite` gates.
- **Just-in-time, sliced — this is what makes live digest realistic.** Digest **only the
  goal-relevant slice** (the concepts the learner's current goal/question actually needs), NOT the
  whole field. Incremental: extend the graph as the learner strays, reusing cached neighbours.
- **Latency/cost/quality controls:** stream progress to the UI ("finding sources → extracting
  concepts → building map"); cheap-extract + verify-only-high-impact; cap depth; confidence +
  similarity fallback (KnowLP) + user/teacher override; **cache the result** (`digest_cache`) so the
  identical slice is a cache hit next time. No predicted allowlist — the cache only remembers real
  past requests.

> **Impl note (2026-06-20):** Prereq edges use **RefD-style + LLM** as specced: a non-LLM corpus
> reference-distance signal (`litnav/digest/refd.py`) is blended with the LLM judge, and RefD can
> corroborate a judge-rejected high-impact edge (closes audit finding D1). Multi-source digest is
> supported by the code — `sources` is a list, chunks are globally indexed; single-source vs
> multi-source live validation is tracked as action A4.
>
> **Deferred → OW-4/OW-7:** Incremental graph extension ("extend the graph as the learner strays
> into new sub-areas") — this requires the teach/assess outer-loop awareness built in OW-4 and the
> live cold-start path from OW-7.
>
> **Deferred → OW-6:** User/teacher edge override UI; streaming digest progress to the frontend
> ("finding sources → extracting concepts → building map") — both require the dual-frontend work
> in OW-6.

### 6.3 TEACH/ASSESS — **LangGraph inner loop, not a skill** (reuse + extend `main`)
- Add **goal elicitation** node (1 turn → `learner_goal.goal_type`), which sets the Bloom ceiling
  and pacing for the existing `orient → teach_kp → assess_next → grade_kp → route` loop.
- **Teach** reads strategy from a cheap policy (goal × expertise × KT-state); reteach includes a
  **metacognitive prompt**. **Never** reveal answers first (anti-over-help).
- **Assess** = Bloom-leveled item from `quiz_items`; **distractors** generated by a cheap model via
  overgenerate-and-rank; **SAQUET-style flaw gate** rejects bad items; **difficulty** from
  LLM-simulation/IRT (comparison prompting), stored as `irt_b` — the **simulator may be a
  deliberately WEAKER/cheaper model** (lit-review: weaker models reproduce the student error
  distribution better, and it's cheaper); **grading** rubric-based with **uncertainty escalation**
  (low confidence → frontier or human-flag), 0–5 scale internally.
- **Spacing:** mastered concepts enter the FSRS `review_queue`; cadence scales inverse to recall
  probability; over-practice fast-forward at `P(mastery) ≥ 0.95`.
- **Mastery is an estimate, and we triangulate it (lit-review risk B).** 25 years of KT rarely
  validate mastery against durable post-tests. So a mastered concept schedules a **delayed retention
  probe** (a spaced re-quiz from `review_queue`); the learner model logs predicted-vs-actual at the
  probe. This is an honest internal-validation signal — surfaced, never claimed as proof of durable
  learning.

### 6.4 `make-artifact` (multi-format output — **format is CHOSEN per scenario, not fixed**)
- **In:** `{concept_ids, scenario: {goal_type, user_request, content_kind}, format?}`
  (`format` optional override; otherwise the skill **selects** it).
- **Out:** `{artifact_path, format, citations}`
- **Format-selection matrix** (research-grounded — Mayer's multimedia principles; concept-map &
  worked-example literature; testing effect):

  | Scenario / goal | Best artifact | Why |
  |---|---|---|
  | Understand how concepts relate / see structure (survey, systematic) | **concept-map / mind-map** (Mermaid/markmap from `concept_graph()`) | maps win for relationships, dependencies, cross-links |
  | Quick recall / reference / crash-course | **concise notes** (Cornell-style: cues + summary, NOT verbatim) | forces selective processing; verbatim notes hurt |
  | Learn a procedure / applied / "how to do X" | **worked example** (+ one practice item) | lowest cognitive load for novices; pair with practice for transfer |
  | Present / teach others / structured linear walkthrough | **slides** (Marp Markdown→pptx now; python-pptx if editable decks needed) | linear narrative format |
  | Deep mastery | **combination**: map (structure) + notes (detail) + worked examples (procedure) | cover all three |
- **Cross-cutting rules (all formats):** follow Mayer (concise, graphics+text, exclude extraneous);
  **end each segment with a retrieval prompt** (testing effect); every artifact carries source
  citations. Slides pipeline = multi-stage decompose → strict JSON schema → thin DSL over the
  renderer.
- **Build order:** mind-map first (reuses `concept_graph()`, ~free), then notes, then slides
  (Marp), then worked-example. Renderer choice is researched per format, not defaulted to PPT.

### 6.5 `recommend-next` (NEXT-STEP)
- **In:** `{session_id}`
- **Out:** `{next_concepts: [{concept_id, reason, prereqs_met}], rationale}`
- **How:** **hard prerequisite constraint + soft ranker** — filter to concepts whose prereqs are
  mastered (or reachable via a similarity edge), rank by expected mastery gain (KT) with an LLM
  tie-break. RL ranking is post-MVP.

## 7. Outer agent loop

A ReAct loop with a Plan-and-Solve front pass that decides stage order from state:
`no graph for this domain → find-sources → digest-corpus`; `graph exists → teach`; `concept off the
current graph → digest just that sub-area or induce`; `session end → recommend-next`;
`user asks for a deck/notes/map → make-artifact`. Tool-call budget capped; each decision logged to
the Glass-box.

## 8. Frontend (dual surface)
- **Product Chat:** clean conversation; artifacts appear as download cards; honest, grounded.
- **Glass-box:** extend the existing panel with: **source-discovery list** (with authority scores),
  **live digest-graph build** (prereq solid / similarity dashed / induced dotted), **learner model**
  (mastery + IRT θ), **cost meter** (`cost_ledger`), **artifact previews**, and the existing
  route/citation/flow panels.

## 9. Milestones (each → its own writing-plans plan)

- **OW-0 — Cost spine:** `MODEL_REGISTRY` + `router.py` + `cost_ledger` + metering + budget caps.
  *Gate:* every existing test still green; a synthetic run shows per-call metering. **Build first.**
- **OW-1 — Data model:** schema additions (similarity edges, goal, review_queue, distractors,
  irt_b, source_type, cost_ledger) + repo writers + migration of `main`'s fixtures.
- **OW-2 — `digest-corpus` skill (offline-fixture first):** just-in-time **sliced** extraction +
  prereq/similarity edges + verify pass + confidence + **edge-accuracy spot-check** + **result
  caching** (`digest_cache`). *Gate:* digest a fixed source set → graph matches a golden graph
  offline; a second request for the same slice hits the cache; the edge-accuracy sample metric is
  computed and surfaced.
- **OW-3 — `find-sources` skill:** intent routing + adapters (arXiv/Wikipedia/youtube first) +
  ranking + cache. *Gate:* offline fixture sources; one live smoke test.
- **OW-4 — TEACH/ASSESS extensions:** goal elicitation + metacognitive reteach + Bloom/distractor/
  difficulty(weaker-simulator)/uncertainty grading + FSRS queue + **delayed retention probe** +
  **pedagogical-error-cost escalation**. *Gate:* reuse + extend existing verify_m* gates; a retention
  probe is scheduled and predicted-vs-actual logged.
- **OW-5 — `make-artifact` skill (scenario-selected format):** mind-map → notes → slides (Marp) →
  worked-example, with the §6.4 selection matrix. *Gate:* render map/notes/deck offline from a
  fixture graph; format-selector picks the right form per scenario.
- **OW-6 — `recommend-next` + outer agent loop wiring + dual-frontend panels.**
- **OW-7 — live cold-start digest:** end-to-end "ask a brand-new topic → live sliced digest →
  teach" with streamed progress. (For the demo, the shown topic's cache is pre-filled so it's
  instant; a genuinely fresh topic shows the real cold path.)

## 10. Verification strategy
- **Offline determinism preserved:** all skills have a `provider=none` fixture path; the existing
  107+ tests and `verify_m0..m3` gates must stay green throughout.
- **New gates:** `verify_cost` (metering + budget cap fires), `verify_digest` (golden-graph match),
  `verify_artifact` (deck/map renders from fixture).
- **Live smoke tests** are manual and metered (one per skill), never in the offline gate.

> **Cross-link (2026-06-20):** See `docs/2026-06-20-spec-compliance-audit.md` (2026-06-20 full
> OW-0..OW-3 audit) and `docs/2026-06-20-open-world-live-first-reaudit.md` (live-first doctrine
> that supersedes the original §10 offline-gate posture).

## 11. Decisions (resolved 2026-06-20)
1. ✅ **Learner-model backbone:** extend `main`'s BKT-lite + a lightweight **Rasch placement**;
   adopt a CAT library only if/when item-selection is needed.
2. ✅ **Artifacts are scenario-adaptive, not slides-by-default** (see §6.4 matrix). Slides
   specifically use **Marp** first. Mind-map/notes/worked-example are first-class forms.
3. ✅ **Models:** only today's `gpt-4o-mini` + `gpt-4o` are enabled. **Any** other need or better
   option — *including non-OpenAI* — is **record-only** until approved (§5 protocol).
4. ✅ **Default = live digest on demand (every slice is "cold"); no pre-picked "warm domain"**
   (that's unrealistic). The only "warm" is a **pure results cache** (§4.3) — don't re-digest an
   identical slice already computed; it remembers only real past requests, never predictions, and
   the system runs fine with an empty cache. Live cold-start digest is realistic *because* it is
   just-in-time and **sliced** (§6.2). The demo pre-fills one cache entry for its shown topic
   (staging convenience).

## 12. Cost & responsible-AI notes
- Honest framing: ITS gains are modest (meta-analysis g≈0.27); mastery is an **estimate**, surfaced
  as such. Worked examples are the strongest lever — favor them for novices.
- No new paid model is enabled without explicit approval (§5 protocol).
- Distractor/difficulty SOTA shows **small fine-tuned models beat GPT-4o** — reinforces using the
  `cheap` tier for QG, reserving `frontier` for cold-start explanation only.

## 13. Evidence-based risks & mitigations (from the literature review)

The [literature review](2026-06-20-open-world-literature-review.md) flagged two places where the
evidence is genuinely thin. We do not pretend otherwise; each has a designed-in mitigation.

| # | Risk (what the evidence does NOT establish) | Mitigation in this spec |
|---|---|---|
| **A** | **On-the-fly prerequisite-edge accuracy is untested.** Prereq extraction is benchmarked on closed corpora; accuracy when built live from open-web sources is unknown and likely worse. | Prereq edges are a **soft constraint + similarity fallback** (§6.2, KnowLP), never a hard gate; **verify pass** + confidence on high-impact edges; **edge-accuracy spot-check** metric surfaced in the Glass-box (§6.2); below threshold → keep as similarity/flagged. |
| **B** | **No end-to-end study of an autonomous open-domain tutor → durable learning.** All evidence is component-level or human-tutor-mediated (Tutor CoPilot); mastery flags are rarely validated against post-tests. | Mastery is surfaced as an **estimate**; a **delayed retention probe** logs predicted-vs-actual per concept (§6.3); honest framing in the UI, never a durable-learning claim. |

Two further evidence-driven design choices (consensus, not risk): **the tutor LLM never judges
correctness/mastery** (externalize to KT — "Confirming Correct, Missing the Rest"; "Specialised KT
Models Outperform LLMs"); **routing is priced against pedagogical-error cost, not token cost** (§5).

> **Cross-link (2026-06-20):** See `docs/2026-06-20-spec-compliance-audit.md` (2026-06-20 full
> OW-0..OW-3 audit) and `docs/2026-06-20-open-world-live-first-reaudit.md` (live-first doctrine
> that supersedes the original §10 offline-gate posture).
