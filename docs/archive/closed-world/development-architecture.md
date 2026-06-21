# LitNavigator Development Architecture

This document translates the product spec into the engineering shape we should build first. The goal is not to implement the full research-literature tutor immediately; the goal is to make the first runnable vertical slice small, honest, and easy to verify.

## Current Repository State

**M0–M3 are implemented and green** (`verify_m0/m1/m2/m3` pass fully offline; see the README roadmap). The repository contains the runnable `litnav/` package (state, storage, graph + LangGraph builder, nodes, llm seam, ui panel), seed fixtures, tests, and CLI demos. The section below documents the original engineering shape; it remains accurate as the module map. M4 (polish) and the interactive product UI are the remaining work.

## First Engineering Principle

Build a fake-data vertical slice before building ingestion.

The shortest path to proof is:

1. Seed a tiny local corpus.
2. Run one session through the tutor state machine.
3. Write learner state, route changes, quiz attempts, and decisions to SQLite.
4. Verify those writes with a script.

Only after that should we add paper ingestion, embeddings, full retrieval, or richer UI.

## Target Project Skeleton

```text
litnavigator/
├── litnav/
│   ├── __init__.py
│   ├── app.py                  # CLI or thin local UI entry point
│   ├── config.py               # env/config loading
│   ├── state.py                # NavState and ConceptState types
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── builder.py          # compose the M0/M1 state machine
│   │   └── router.py           # tutor_router and route decisions
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── planner.py
│   │   ├── teach.py
│   │   ├── check.py
│   │   ├── grade.py
│   │   ├── diagnose.py
│   │   ├── replan.py
│   │   └── induce.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── schema.py           # SQLite DDL for the minimal domain tables
│   │   ├── seed.py             # deterministic seed fixture
│   │   └── repo.py             # typed read/write helpers
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── fake.py             # M0 deterministic evidence lookup
│   ├── llm/                    # M2/M3: provider abstraction (qwen + none fallback)
│   │   ├── __init__.py
│   │   └── client.py
│   ├── ui/                     # M1+: thin FastAPI/Jinja trace panel
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── templates/
│   └── evaluation/
│       ├── __init__.py
│       └── verify_m0.py        # gate script for M0
├── tests/
│   ├── test_router.py
│   ├── test_bkt.py
│   ├── test_storage.py
│   └── test_m0_flow.py
├── data/
│   ├── seed/
│   │   └── rag_demo.json       # tiny deterministic topic fixture
│   └── runtime/                # generated SQLite DB, ignored by git
├── docs/
│   ├── development-architecture.md
│   ├── engineering-slices.md
│   └── m0-walking-skeleton.md
├── requirements.txt
├── .env.example
└── README.md
```

## Boundary Decisions

### State Machine

The state machine owns flow control only. It should decide which node runs next and carry `NavState` between nodes. It should not directly query SQLite from arbitrary places.

### Nodes

Each node owns one transformation:

- `planner`: create the initial route from the concept DAG.
- `teach`: produce a grounded teaching turn from the current concept and evidence.
- `check`: select or present a quiz item.
- `grade`: score the answer, update mastery/confidence, and detect misconceptions.
- `diagnose`: identify a missing prerequisite.
- `replan`: insert or reorder route steps and increment `route_version`.
- `induce`: add machine-derived scaffolding from evidence. Fixture-backed by default; with a provider set (`LITNAV_LLM_PROVIDER=openai`/`qwen`) the LLM proposes the misconception (wrong vs. correct model) and labels evidence strength over the real chunks, while confidence stays rule-computed.

### Storage

Storage should expose small functions such as `record_decision`, `record_quiz_attempt`, `upsert_learner_state`, and `write_route_steps`. Nodes call these helpers instead of embedding SQL.

### Retrieval

M0 retrieval is deterministic and fixture-backed. It can return the right evidence chunk by `concept_id`.

M1 can add SQLite FTS5. Chroma and embeddings should wait until after the state machine and acceptance gates are stable.

### UI

Do not build a full UI for M0. A CLI transcript or tiny local panel is enough if it shows:

- current concept,
- quiz answer,
- route before/after,
- decision rationale,
- SQLite verification output.

## Minimal Domain Tables for M0/M1

Start with these tables:

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

Delay these until M2/M3:

- `misconceptions`
- `tutor_turns`
- `induction_log`
- `citations`
- `concept_paper_rank`

## Non-Goals Before M1 Passes

- No live arXiv/OpenAlex/Semantic Scholar fetch.
- No GROBID.
- No Chroma or SPECTER2.
- No full automatic concept DAG construction.
- No polished production UI.
- No multi-user auth.

These are useful later, but they do not prove the product's core loop.
