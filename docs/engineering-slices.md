# Engineering Slices

LitNavigator should be built as a ladder of runnable slices. Each slice must be demoable, recordable, and verifiable before the next slice starts.

## Slice 0: Planning Package

**Status:** current repository.

**Contains:**

- product README,
- full build spec,
- static architecture page,
- development docs.

**Does not contain:**

- runnable Python package,
- dependency lock,
- seed database,
- tests,
- app entry point.

**Exit criteria:**

- README honestly says the code has not started.
- M0 scope is small enough to implement in one focused pass.
- implementation plan exists under `docs/superpowers/plans/`.

## Slice 1: M0 Fake-Data Walking Skeleton

**Goal:** prove the loop writes real state without depending on real ingestion or embeddings.

**Build:**

- package skeleton under `litnav/`,
- deterministic seed fixture for a small RAG topic,
- SQLite schema for core tables,
- basic route planner,
- fixed quiz item,
- BKT-lite mastery update,
- decision logging,
- M0 verification script.

**Demo:**

Run one session:

```text
goal -> route -> concept -> quiz -> answer -> grade -> advance
```

Then show that SQLite contains:

- one session,
- route steps,
- learner-state update,
- quiz attempt,
- decision log.

**Gate G0:**

`python -m litnav.evaluation.verify_m0` passes.

## Slice 2: M1 Navigator

**Goal:** prove the route changes because of learner state.

**Build:**

- the real LangGraph `StateGraph` (nodes + conditional edges) + `SqliteSaver`, replacing M0's procedural flow,
- target-only route planning (prereqs assumed known, inserted on a revealed gap),
- prerequisite diagnosis,
- `replan` with `route_version + 1`,
- evidence-bound quiz,
- traceable rationale,
- a thin FastAPI web panel (left chat / right route+evidence) as the recordable artifact.

**Demo:**

Answer a negative-sampling prerequisite question wrong. The system inserts the missing prerequisite before continuing.

**Gate G1:**

- correct answer advances,
- wrong prerequisite answer replans,
- rationale cites quiz result and concept edge,
- SQLite shows `route_version` changed.

## Slice 3: M2 Tutor

**Goal:** prove it teaches, checks, detects misconception, and reteaches differently.

**Build:**

- `teach` with cited chunks,
- the `llm/client` provider abstraction (qwen + deterministic `none` fallback),
- misconception detection (LLM path + deterministic fallback),
- `reteach` with unused strategy selection,
- `concede` route for exhausted reteach attempts,
- `tutor_turns`,
- confidence display separated from mastery.

**Demo:**

Trigger `dr_is_keyword_match`, reteach with an analogy, then pass a parallel item.

**Gate G2:**

- three route branches exist: advance, reteach, diagnose/replan,
- `concede` terminates instead of looping,
- post-check score improves over pre-check score,
- no teaching assertion lacks a chunk id.

## Slice 4: M3 Literature Induction

**Goal:** prove the novel square: scaffolding induced from the living literature.

**Build:**

- `induce_scaffold` (LLM extraction over ingested chunks when `provider=qwen`; offline fixture fallback when `none`),
- `source='induced'` provenance,
- `confidence_basis` (rule-computed, never LLM-emitted),
- induced prerequisite edge,
- induced misconception,
- UI/trace distinction between curated and induced scaffolding.

**Demo:**

User asks about `hard_negative_mining`, which is off the curated skeleton. The system induces `negative_sampling -> hard_negative_mining`, mines one misconception, and teaches with evidence.

**Gate G3:**

- every induced output has evidence,
- confidence is rule-computed,
- induced elements are visibly marked as machine-derived,
- the induced element is used in the route or teaching turn.

## Slice 5: M4 Polish

Only after M3 is stable:

- trace UI polish,
- coverage warnings,
- jump-step pushback,
- hybrid retrieval,
- Chroma/vector retrieval,
- cross-session memory,
- richer concept graph.
