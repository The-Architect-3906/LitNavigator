# M0 Walking Skeleton

M0 is a fake-data vertical slice. It should feel almost embarrassingly small. That is the point.

## Purpose

M0 proves that the core loop exists as software:

```text
init session -> plan route -> select concept -> present quiz -> grade -> write state -> advance
```

It does not prove literature induction, RAG quality, or teaching quality yet.

## Seed Fixture

Use one tiny topic: `RAG for scientific QA`.

Minimum fixture:

- 4 concepts:
  - `dense_retrieval`
  - `negative_sampling`
  - `contrastive_learning`
  - `rag_pipeline`
- 3 prerequisite edges:
  - `dense_retrieval -> rag_pipeline`
  - `negative_sampling -> contrastive_learning`
  - `contrastive_learning -> rag_pipeline`
- 2 papers or paper-like records.
- 4 evidence chunks, one per concept.
- 4 quiz items, one per concept.

The fixture can be JSON. It should be deterministic and checked into git.

## M0 Flow

1. `init_or_load_state` creates a session and default learner state for all seed concepts.
2. `planner` topo-sorts the seed concept DAG.
3. `select_next_concept` chooses the first pending concept.
4. `retrieve_evidence` returns the seed chunk for that concept.
5. `check` returns one fixed quiz item.
6. `grade` scores a deterministic answer and updates mastery/confidence.
7. `tutor_router` advances if mastery passes the threshold.
8. `advance` marks the route step done.
9. storage writes the audit trail.

## M0 Tables

Create only:

- `concepts`
- `concept_edges`
- `papers`
- `paper_chunks`
- `quiz_items`
- `sessions`
- `learner_state`
- `quiz_attempts`
- `route_steps`
- `decisions`

Use JSON text columns where useful. Avoid schema perfection.

## M0 Verification

The gate script should create a fresh local SQLite DB, seed it, run one deterministic session, and assert:

- a session row exists,
- at least one route step exists,
- at least one learner state row changed from its initial mastery,
- at least one quiz attempt exists,
- at least one decision row exists,
- the run performs no network calls.

Suggested command:

```bash
python -m litnav.evaluation.verify_m0
```

Expected output:

```text
G0 PASS: session written
G0 PASS: route written
G0 PASS: learner_state updated
G0 PASS: quiz_attempt written
G0 PASS: decision written
G0 PASS: offline run
```

## M0 Definition of Done

- `pytest` passes.
- `python -m litnav.evaluation.verify_m0` passes.
- README quick start points to the M0 command.
- A short transcript can be recorded without editing code.

## Explicit Deferrals

- No LLM call.
- No embeddings.
- No Chroma.
- No live paper fetch.
- No PDF parsing.
- No induced scaffold.
- No polished browser UI.
