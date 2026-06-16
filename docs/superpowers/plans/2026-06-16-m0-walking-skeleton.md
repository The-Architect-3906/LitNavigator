# M0 Walking Skeleton Implementation Plan

> **⚠️ ARCHIVED / HISTORICAL — M0 is implemented and green (`verify_m0`).** This was the original M0 construction plan; the unchecked `[ ]` boxes are historical. See the README roadmap and `docs/milestones.md` for current state.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable LitNavigator vertical slice with deterministic seed data, SQLite persistence, a simple tutor flow, and an M0 verification gate.

**Architecture:** Start with a small Python package and fake retrieval. The state machine can be a plain function sequence for M0, as long as node boundaries match the future LangGraph design and all durable state is written through storage helpers.

**Tech Stack:** Python 3.11, SQLite, pytest, standard-library JSON/dataclasses/typing.

---

## File Structure

- Create: `requirements.txt` with `pytest` and no heavyweight runtime dependencies yet.
- Create: `.env.example` with placeholders but no required API key for M0.
- Create: `litnav/state.py` for `ConceptState`, `NavState`, and BKT helpers.
- Create: `litnav/storage/schema.py` for minimal SQLite DDL.
- Create: `litnav/storage/seed.py` for loading `data/seed/rag_demo.json`.
- Create: `litnav/storage/repo.py` for all database writes and reads.
- Create: `litnav/retrieval/fake.py` for deterministic evidence lookup.
- Create: `litnav/graph/router.py` for `tutor_router`.
- Create: `litnav/graph/builder.py` for the M0 flow runner.
- Create: `litnav/evaluation/verify_m0.py` for the G0 gate.
- Create: `tests/` coverage for BKT, routing, storage, and the M0 flow.

---

### Task 1: Package and Seed Skeleton

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `litnav/__init__.py`
- Create: `litnav/graph/__init__.py`
- Create: `litnav/storage/__init__.py`
- Create: `litnav/retrieval/__init__.py`
- Create: `litnav/evaluation/__init__.py`
- Create: `data/seed/rag_demo.json`

- [ ] **Step 1: Add dependencies**

```text
pytest>=8.0
```

- [ ] **Step 2: Add `.env.example`**

```text
# M0 runs without external services.
LITNAV_DB_PATH=data/runtime/litnav.sqlite
LITNAV_LLM_PROVIDER=none
LITNAV_LLM_API_KEY=
```

- [ ] **Step 3: Add empty package markers**

Each `__init__.py` can contain:

```python
"""LitNavigator package."""
```

- [ ] **Step 4: Add deterministic seed fixture**

This fixture is **M1-ready**: it carries `targets` and an `evaluation` concept so M1 reuses it without a rewrite. `negative_sampling` is a prerequisite edge into `contrastive_learning` but is **not** a target — so the planner leaves it out of the initial route, and M1's `replan` can insert it on a quiz failure.

```json
{
  "topic": "RAG for scientific QA",
  "targets": ["dense_retrieval", "contrastive_learning", "rag_pipeline", "evaluation"],
  "concepts": [
    {"id": 1, "slug": "dense_retrieval", "name": "Dense retrieval", "frontier_flag": "consensus"},
    {"id": 2, "slug": "negative_sampling", "name": "Negative sampling", "frontier_flag": "consensus"},
    {"id": 3, "slug": "contrastive_learning", "name": "Contrastive learning", "frontier_flag": "consensus"},
    {"id": 4, "slug": "rag_pipeline", "name": "RAG pipeline", "frontier_flag": "consensus"},
    {"id": 5, "slug": "evaluation", "name": "Evaluation and hallucination", "frontier_flag": "consensus"}
  ],
  "edges": [
    {"prereq_concept": 1, "target_concept": 4, "edge_type": "prerequisite", "source": "curated", "confidence": 1.0},
    {"prereq_concept": 2, "target_concept": 3, "edge_type": "prerequisite", "source": "curated", "confidence": 1.0},
    {"prereq_concept": 3, "target_concept": 4, "edge_type": "prerequisite", "source": "curated", "confidence": 1.0},
    {"prereq_concept": 4, "target_concept": 5, "edge_type": "prerequisite", "source": "curated", "confidence": 1.0}
  ],
  "papers": [
    {"id": 1, "title": "Dense Retrieval for Scientific Question Answering", "year": 2023},
    {"id": 2, "title": "Contrastive Learning Foundations for Retrieval", "year": 2022}
  ],
  "chunks": [
    {"id": "c_dense_1", "paper_id": 1, "concept_id": 1, "text": "Dense retrieval represents queries and documents in an embedding space, then retrieves nearest neighbors by vector similarity."},
    {"id": "c_negative_1", "paper_id": 2, "concept_id": 2, "text": "Negative sampling teaches a model to distinguish relevant examples from non-relevant alternatives during contrastive training."},
    {"id": "c_contrastive_1", "paper_id": 2, "concept_id": 3, "text": "Contrastive learning improves representations by pulling positive pairs together and pushing negative pairs apart."},
    {"id": "c_rag_1", "paper_id": 1, "concept_id": 4, "text": "A RAG pipeline retrieves external evidence and conditions generation on that evidence to reduce unsupported answers."},
    {"id": "c_eval_1", "paper_id": 1, "concept_id": 5, "text": "Evaluation of RAG checks whether generated answers are grounded in retrieved evidence and flags unsupported (hallucinated) claims."}
  ],
  "quiz_items": [
    {"id": 1, "concept_id": 1, "question": "Dense retrieval mainly compares documents using what representation?", "answer_key": "embedding vectors", "evidence_chunk_id": "c_dense_1", "source_paper_id": 1},
    {"id": 2, "concept_id": 2, "question": "What role do negatives play in contrastive training?", "answer_key": "non-relevant alternatives", "evidence_chunk_id": "c_negative_1", "source_paper_id": 2},
    {"id": 3, "concept_id": 3, "question": "What happens to positive pairs in contrastive learning?", "answer_key": "they are pulled together", "evidence_chunk_id": "c_contrastive_1", "source_paper_id": 2},
    {"id": 4, "concept_id": 4, "question": "Why does RAG retrieve evidence before generation?", "answer_key": "to condition generation on external evidence", "evidence_chunk_id": "c_rag_1", "source_paper_id": 1},
    {"id": 5, "concept_id": 5, "question": "What does RAG evaluation primarily check for?", "answer_key": "answers grounded in retrieved evidence", "evidence_chunk_id": "c_eval_1", "source_paper_id": 1}
  ]
}
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example litnav data/seed/rag_demo.json
git commit -m "chore: add M0 package and seed skeleton"
```

### Task 2: State and BKT

**Files:**
- Create: `litnav/state.py`
- Create: `tests/test_bkt.py`

- [ ] **Step 1: Write the failing tests**

```python
from litnav.state import bkt_update, confidence_update, initial_concept_state


def test_bkt_correct_taught_reaches_money_shot_range():
    updated = bkt_update(0.40, correct=True, taught=True)
    assert 0.82 <= updated <= 0.83


def test_confidence_increases_with_observations():
    assert confidence_update(1) == 0.4
    assert confidence_update(2) > confidence_update(1)
    assert confidence_update(5) > confidence_update(3)


def test_initial_concept_state_separates_mastery_and_confidence():
    state = initial_concept_state()
    assert state["mastery"] == 0.4
    assert state["confidence"] == 0.0
    assert state["n_observations"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bkt.py -v`

Expected: FAIL because `litnav.state` does not exist.

- [ ] **Step 3: Implement state helpers**

```python
from __future__ import annotations

from typing import Literal, TypedDict


class ConceptState(TypedDict):
    mastery: float
    confidence: float
    n_observations: int
    evidence: list[dict]
    held_misconceptions: list[str]
    tried_strategies: list[str]
    depth: Literal["recall", "apply", "explain"]


def initial_concept_state() -> ConceptState:
    return {
        "mastery": 0.4,
        "confidence": 0.0,
        "n_observations": 0,
        "evidence": [],
        "held_misconceptions": [],
        "tried_strategies": [],
        "depth": "recall",
    }


def bkt_update(p: float, correct: bool, taught: bool) -> float:
    slip = 0.10
    guess = 0.20
    transit = 0.30
    if correct:
        post = p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)
    else:
        post = p * slip / (p * slip + (1 - p) * (1 - guess))
    return post + (1 - post) * transit if taught else post


def confidence_update(n_observations: int) -> float:
    return round(1 - 0.6**n_observations, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bkt.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add litnav/state.py tests/test_bkt.py
git commit -m "feat: add M0 learner state helpers"
```

### Task 3: Minimal SQLite Storage

**Files:**
- Create: `litnav/storage/schema.py`
- Create: `litnav/storage/seed.py`
- Create: `litnav/storage/repo.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage test**

```python
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data


def test_seed_demo_data_writes_core_tables(tmp_path):
    db_path = tmp_path / "litnav.sqlite"
    conn = sqlite3.connect(db_path)
    init_db(conn)
    seed_demo_data(conn, "data/seed/rag_demo.json")

    assert conn.execute("select count(*) from concepts").fetchone()[0] == 5
    assert conn.execute("select count(*) from concept_edges").fetchone()[0] == 4
    assert conn.execute("select count(*) from paper_chunks").fetchone()[0] == 5
    assert conn.execute("select count(*) from quiz_items").fetchone()[0] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -v`

Expected: FAIL because storage modules do not exist.

- [ ] **Step 3: Implement schema**

Create tables named exactly as the test expects: `concepts`, `concept_edges`, `papers`, `paper_chunks`, `quiz_items`, `sessions`, `learner_state`, `quiz_attempts`, `route_steps`, `decisions`.

- [ ] **Step 4: Implement seed loading**

Read `data/seed/rag_demo.json`, insert concepts, edges, papers, chunks, and quiz items, then commit the transaction.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_storage.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add litnav/storage tests/test_storage.py
git commit -m "feat: add M0 SQLite schema and seed loader"
```

### Task 4: Router and M0 Flow

**Files:**
- Create: `litnav/graph/router.py`
- Create: `litnav/retrieval/fake.py`
- Create: `litnav/graph/builder.py`
- Create: `tests/test_router.py`
- Create: `tests/test_m0_flow.py`

- [ ] **Step 1: Write router tests**

```python
from litnav.graph.router import tutor_router


def test_router_advances_when_mastered():
    state = {
        "current_concept_id": 1,
        "mastery_threshold": 0.8,
        "learner_state": {1: {"mastery": 0.82, "held_misconceptions": []}},
        "concept_dag": {1: []},
        "reteach_count": {},
    }
    assert tutor_router(state) == "advance"


def test_router_diagnoses_when_prereq_missing():
    state = {
        "current_concept_id": 4,
        "mastery_threshold": 0.8,
        "learner_state": {
            1: {"mastery": 0.4, "held_misconceptions": []},
            4: {"mastery": 0.4, "held_misconceptions": []},
        },
        "concept_dag": {4: [1]},
        "reteach_count": {},
    }
    assert tutor_router(state) == "diagnose"
```

- [ ] **Step 2: Implement `tutor_router`**

Use the decision order from `litnavigator-build-spec.md`: mastered, reteachable misconception, missing prereq, concede.

- [ ] **Step 3: Write M0 flow test**

Run one deterministic session against a temporary SQLite DB and assert that `learner_state`, `quiz_attempts`, `route_steps`, and `decisions` have rows.

- [ ] **Step 4: Implement fake retrieval and `run_m0_session`**

`run_m0_session(conn, answer="embedding vectors")` should seed learner state, choose dense retrieval, grade the fixed answer, update mastery/confidence, write a quiz attempt, write a decision, and mark the route step done.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_router.py tests/test_m0_flow.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add litnav/graph litnav/retrieval tests/test_router.py tests/test_m0_flow.py
git commit -m "feat: add M0 tutor flow"
```

### Task 5: M0 Verification Gate and README Update

**Files:**
- Create: `litnav/evaluation/verify_m0.py`
- Modify: `README.md`

- [ ] **Step 1: Implement verification gate**

`python -m litnav.evaluation.verify_m0` should create `data/runtime/litnav-m0.sqlite`, run the M0 session, print each G0 PASS line, and exit non-zero on any failed assertion.

- [ ] **Step 2: Run verification**

Run: `python -m litnav.evaluation.verify_m0`

Expected:

```text
G0 PASS: session written
G0 PASS: route written
G0 PASS: learner_state updated
G0 PASS: quiz_attempt written
G0 PASS: decision written
G0 PASS: offline run
```

- [ ] **Step 3: Run full tests**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 4: Update README quick start**

Replace the planning-state warning with the M0 command once the command exists:

```bash
pip install -r requirements.txt
python -m litnav.evaluation.verify_m0
```

- [ ] **Step 5: Commit**

```bash
git add litnav/evaluation/verify_m0.py README.md
git commit -m "feat: add M0 verification gate"
```

## Self-Review

- Spec coverage: This plan covers M0 only. M1-M3 remain intentionally out of scope.
- Placeholder scan: No step relies on undefined future services or live APIs.
- Type consistency: `ConceptState`, table names, and command names match across tasks.

Plan complete and saved to `docs/superpowers/plans/2026-06-16-m0-walking-skeleton.md`.
