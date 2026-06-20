# Open-World LitNavigator — Architecture Spec

**Date:** 2026-06-20 · **Branch:** `feat/open-world-digest`
**Source of truth for design rationale:** [research brief](2026-06-20-open-world-research-brief.md)

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

### 4.2 Learner model (the ground truth)
- `learner_state(session_id, concept_id, mastery REAL, confidence REAL, n_observations,
  held_misconceptions_json, tried_strategies_json, irt_theta REAL NULL)` — extend with Rasch/IRT
  ability `irt_theta`.
- `learner_goal(session_id, goal_text, goal_type ∈ {mastery, functional, survey}, target_concepts_json,
  created_at)` — **new (goal elicitation).**
- `review_queue(session_id, concept_id, due_at, fsrs_state_json)` — **new (FSRS spacing).**

### 4.3 Digest cache & cost
- `domain_digest(domain_key, status ∈ {warm, cold, building}, graph_version, built_at,
  human_checked BOOL)` — warm = precomputed + human-checked; demo main domain is warm.
- `cost_ledger(session_id, ts, stage, model, input_tokens, output_tokens, usd, cache_hit BOOL)` —
  **new; backs the live cost meter and per-session budget cap.**

## 5. The model router & cost governance (build this FIRST — everything depends on it)

A single chokepoint: `litnav/llm/router.py` wraps `llm/client.py`.

- **Three tiers**, declared in a registry (`MODEL_REGISTRY`): `cheap` (default `gpt-4o-mini`),
  `mid` (reserved; record-only until approved), `frontier` (default `gpt-4o`, cold-start
  explanation + flagged escalations only). Routing decisions that are *not* generative (mastery
  update, item selection) never call an LLM.
- **Escalation gate:** start at `cheap`; escalate to `frontier` only on an explicit signal
  (cold-start concept explanation; low grader confidence; user-facing teaching for a Mastery-goal
  learner). Logged with reason.
- **Caching:** prompt caching on stable prefixes (learner profile, SKILL.md body, digest);
  semantic result cache keyed by `(stage, normalized_input_hash)` with cosine≥0.92.
- **Precompute:** warm domains digested offline + human-checked; live digest only for cold domains,
  behind a quality gate.
- **Metering & budget:** every call writes `cost_ledger`; a per-session `token_budget` hard-caps
  spend; alert at 80%; tool-loop caps prevent runaway. Glass-box shows the live meter.
- **Model-need protocol:** the only ENABLED models are today's (`gpt-4o-mini` cheap, `gpt-4o`
  frontier). **Any** other need or better option — **including non-OpenAI providers** (Anthropic,
  open-weights, a DPO-tuned tutor model, a reranker, etc.) — is added to `MODEL_REGISTRY` as
  `record-only` (disabled) with a one-line rationale and surfaced for approval. **Never enable a new
  model silently.**

## 6. Stage skills — contracts

Each is an Anthropic Skill (`SKILL.md` + scripts) the outer agent invokes. Contracts are JSON;
each must run offline-deterministically when `provider=none` (return a fixture or a clear error).

### 6.1 `find-sources` (DISCOVER)
- **In:** `{goal_text, intent ∈ {crash-course, systematic, applied, reference, cutting-edge},
  budget}`
- **Out:** `{sources: [{source_type, id, url, title, authority_score, why}], intent_used}`
- **How:** intent classifier → source-type stack → tool calls (OpenAlex/S2/arXiv/Wikipedia/
  youtube-transcript) → BM25 prefilter → SPECTER rerank → dedup → authority score. 2–3 iterative
  rounds for systematic/deep intents.
- **Cost:** metadata-only first; full-text fetch only top-k. Semantic query cache.

### 6.2 `digest-corpus` (DIGEST)
- **In:** `{sources, domain_key}`
- **Out:** `{concepts[], edges[(prereq|similarity), confidence, evidence], keypoints[], quiz_seeds[],
  unverified_edges[]}`
- **How:** chunk+embed → concept/keyphrase extraction (cheap model) → **prereq edges (RefD-style +
  LLM) AND similarity edges** → keypoint+evidence binding + Bloom tag → **verify pass (frontier
  model) on high-impact edges only** → confidence scores. Writes to concept graph; low-confidence
  edges flagged, not silently trusted.
- **Cost/quality:** warm domains precomputed+human-checked; cold domains live behind the gate.

### 6.3 TEACH/ASSESS — **LangGraph inner loop, not a skill** (reuse + extend `main`)
- Add **goal elicitation** node (1 turn → `learner_goal.goal_type`), which sets the Bloom ceiling
  and pacing for the existing `orient → teach_kp → assess_next → grade_kp → route` loop.
- **Teach** reads strategy from a cheap policy (goal × expertise × KT-state); reteach includes a
  **metacognitive prompt**. **Never** reveal answers first (anti-over-help).
- **Assess** = Bloom-leveled item from `quiz_items`; **distractors** generated by a cheap model via
  overgenerate-and-rank; **SAQUET-style flaw gate** rejects bad items; **difficulty** from
  LLM-simulation/IRT (comparison prompting), stored as `irt_b`; **grading** rubric-based with
  **uncertainty escalation** (low confidence → frontier or human-flag), 0–5 scale internally.
- **Spacing:** mastered concepts enter the FSRS `review_queue`; cadence scales inverse to recall
  probability; over-practice fast-forward at `P(mastery) ≥ 0.95`.

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
- **OW-2 — `digest-corpus` skill (offline-fixture first):** extraction + prereq/similarity edges +
  verify pass + confidence; warm-domain precompute path. *Gate:* digest a fixed source set → graph
  matches a golden graph offline.
- **OW-3 — `find-sources` skill:** intent routing + adapters (arXiv/Wikipedia/youtube first) +
  ranking + cache. *Gate:* offline fixture sources; one live smoke test.
- **OW-4 — TEACH/ASSESS extensions:** goal elicitation + metacognitive reteach + Bloom/distractor/
  difficulty/uncertainty grading + FSRS queue. *Gate:* reuse + extend existing verify_m* gates.
- **OW-5 — `make-artifact` skill (scenario-selected format):** mind-map → notes → slides (Marp) →
  worked-example, with the §6.4 selection matrix. *Gate:* render map/notes/deck offline from a
  fixture graph; format-selector picks the right form per scenario.
- **OW-6 — `recommend-next` + outer agent loop wiring + dual-frontend panels.**
- **OW-7 — live high-light:** cold-domain live digest demo path (pre-warmed main domain stays the
  default).

## 10. Verification strategy
- **Offline determinism preserved:** all skills have a `provider=none` fixture path; the existing
  107+ tests and `verify_m0..m3` gates must stay green throughout.
- **New gates:** `verify_cost` (metering + budget cap fires), `verify_digest` (golden-graph match),
  `verify_artifact` (deck/map renders from fixture).
- **Live smoke tests** are manual and metered (one per skill), never in the offline gate.

## 11. Decisions (resolved 2026-06-20)
1. ✅ **Learner-model backbone:** extend `main`'s BKT-lite + a lightweight **Rasch placement**;
   adopt a CAT library only if/when item-selection is needed.
2. ✅ **Artifacts are scenario-adaptive, not slides-by-default** (see §6.4 matrix). Slides
   specifically use **Marp** first. Mind-map/notes/worked-example are first-class forms.
3. ✅ **Models:** only today's `gpt-4o-mini` + `gpt-4o` are enabled. **Any** other need or better
   option — *including non-OpenAI* — is **record-only** until approved (§5 protocol).
4. ⏳ **Deferred to OW-2:** which subject is the pre-digested "warm" baseline vs the live-digested
   "cold" demo domain. Not blocking; decide when building `digest-corpus`.

## 12. Cost & responsible-AI notes
- Honest framing: ITS gains are modest (meta-analysis g≈0.27); mastery is an **estimate**, surfaced
  as such. Worked examples are the strongest lever — favor them for novices.
- No new paid model is enabled without explicit approval (§5 protocol).
- Distractor/difficulty SOTA shows **small fine-tuned models beat GPT-4o** — reinforces using the
  `cheap` tier for QG, reserving `frontier` for cold-start explanation only.
