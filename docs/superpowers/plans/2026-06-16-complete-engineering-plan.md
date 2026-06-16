# LitNavigator Complete Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build LitNavigator from planning package to a recordable M3 competition system, with M4 polish only after the core gates pass.

**Architecture:** Build a vertical slice first, then widen it. M0 proves deterministic state and SQLite writes; M1 proves route adaptation; M2 proves teaching/reteaching; M3 proves literature-induced scaffolding; M4 improves presentation and resilience without risking the latest stable gate.

**Tech Stack:** Python 3.11, SQLite, pytest, LangGraph from M1/M2 onward, optional Chroma/vector retrieval after the deterministic retrieval path is stable, lightweight browser UI or CLI-first UI depending on available time.

---

## File Structure

Create or evolve these files across the plan:

- `requirements.txt`: runtime and test dependencies.
- `.env.example`: local configuration template.
- `data/seed/rag_demo.json`: deterministic M0/M1 fixture.
- `data/seed/rag_m2_demo.json`: misconception and parallel-quiz fixture.
- `data/seed/rag_m3_induction.json`: induced-scaffold fixture and evidence chunks.
- `litnav/state.py`: `ConceptState`, `NavState`, route-state helpers, BKT and confidence functions.
- `litnav/config.py`: env/config loading.
- `litnav/storage/schema.py`: SQLite schema migrations by milestone.
- `litnav/storage/seed.py`: seed loaders for M0-M3 fixtures.
- `litnav/storage/repo.py`: storage helper functions.
- `litnav/retrieval/fake.py`: deterministic fixture retrieval.
- `litnav/retrieval/sqlite.py`: FTS5/BM25 retrieval after M1.
- `litnav/graph/router.py`: `tutor_router` and route decision constants.
- `litnav/graph/builder.py`: state-machine composition.
- `litnav/nodes/planner.py`: initial route planning.
- `litnav/nodes/select_next.py`: select current concept and off-skeleton detection.
- `litnav/nodes/retrieve.py`: evidence lookup.
- `litnav/nodes/teach.py`: grounded teaching turn generation.
- `litnav/nodes/check.py`: quiz/check item selection.
- `litnav/nodes/grade.py`: scoring, misconception detection, mastery/confidence update.
- `litnav/nodes/reteach.py`: alternate explanation strategy selection.
- `litnav/nodes/diagnose.py`: missing-prerequisite diagnosis.
- `litnav/nodes/replan.py`: route insertion and `route_version` increment.
- `litnav/nodes/concede.py`: honest exit when reteach is exhausted.
- `litnav/nodes/induce.py`: evidence-backed scaffold induction.
- `litnav/evaluation/verify_m0.py`: G0 gate.
- `litnav/evaluation/verify_m1.py`: G1 gate.
- `litnav/evaluation/verify_m2.py`: G2 gate.
- `litnav/evaluation/verify_m3.py`: G3 gate.
- `litnav/app.py`: local CLI or thin UI entry point.
- `tests/test_bkt.py`: mastery/confidence tests.
- `tests/test_storage.py`: schema and seed tests.
- `tests/test_router.py`: branch decision tests.
- `tests/test_m0_flow.py`: M0 vertical-slice test.
- `tests/test_m1_replan.py`: route adaptation tests.
- `tests/test_m2_tutor.py`: teach/reteach/concede tests.
- `tests/test_m3_induction.py`: induced scaffold tests.
- `README.md`: status and quick-start updates as gates pass.
- `docs/evaluation.md`: gate command updates when implemented.
- `docs/demo-script.md`: demo transcript updates when gates pass.

---

## Implementation Sequence

Do not skip gates:

```text
M0 -> G0 pass -> M1 -> G1 pass -> M2 -> G2 pass -> M3 -> G3 pass -> M4
```

If a gate fails, fix the current milestone instead of starting the next one.

---

### Task 1: M0 Package, Seed Fixture, and Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `litnav/__init__.py`
- Create: `litnav/config.py`
- Create: `litnav/graph/__init__.py`
- Create: `litnav/nodes/__init__.py`
- Create: `litnav/storage/__init__.py`
- Create: `litnav/retrieval/__init__.py`
- Create: `litnav/evaluation/__init__.py`
- Create: `data/seed/rag_demo.json`

- [ ] **Step 1: Add minimal dependencies**

`requirements.txt`:

```text
pytest>=8.0
```

- [ ] **Step 2: Add environment template**

`.env.example`:

```text
LITNAV_DB_PATH=data/runtime/litnav.sqlite
LITNAV_LLM_PROVIDER=none
LITNAV_LLM_API_KEY=
LITNAV_USE_NETWORK=false
```

- [ ] **Step 3: Add config loader**

`litnav/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/runtime/litnav.sqlite"
    llm_provider: str = "none"
    llm_api_key: str = ""
    use_network: bool = False


def load_settings() -> Settings:
    return Settings(
        db_path=os.getenv("LITNAV_DB_PATH", "data/runtime/litnav.sqlite"),
        llm_provider=os.getenv("LITNAV_LLM_PROVIDER", "none"),
        llm_api_key=os.getenv("LITNAV_LLM_API_KEY", ""),
        use_network=os.getenv("LITNAV_USE_NETWORK", "false").lower() == "true",
    )
```

- [ ] **Step 4: Add package markers**

Each `__init__.py`:

```python
"""LitNavigator package."""
```

- [ ] **Step 5: Add deterministic M0 fixture**

Use the exact fixture shape in `docs/data-contract.md` with four concepts, three edges, two papers, four chunks, and four quiz items.

- [ ] **Step 6: Verify**

Run: `python -m pytest --version`

Expected: pytest prints a version.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example litnav data/seed/rag_demo.json
git commit -m "chore: add M0 package skeleton"
```

### Task 2: M0 State, Storage, and BKT

**Files:**
- Create: `litnav/state.py`
- Create: `litnav/storage/schema.py`
- Create: `litnav/storage/seed.py`
- Create: `litnav/storage/repo.py`
- Create: `tests/test_bkt.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Add BKT tests**

Use the tests from `docs/superpowers/plans/2026-06-16-m0-walking-skeleton.md`, Task 2.

- [ ] **Step 2: Implement `ConceptState` and helpers**

Implement `initial_concept_state`, `bkt_update`, and `confidence_update` exactly as specified in the M0 plan.

- [ ] **Step 3: Add schema test**

`tests/test_storage.py` must assert seed loading writes:

```python
assert conn.execute("select count(*) from concepts").fetchone()[0] == 4
assert conn.execute("select count(*) from concept_edges").fetchone()[0] == 3
assert conn.execute("select count(*) from paper_chunks").fetchone()[0] == 4
assert conn.execute("select count(*) from quiz_items").fetchone()[0] == 4
```

- [ ] **Step 4: Implement M0 tables**

Create these tables:

```text
concepts
concept_edges
papers
paper_chunks
quiz_items
sessions
learner_state
quiz_attempts
route_steps
decisions
```

Use the column contract in `docs/data-contract.md`.

- [ ] **Step 5: Implement repository helpers**

`litnav/storage/repo.py` must expose:

```python
create_session(conn, session_id: str, topic: str) -> None
initialize_learner_state(conn, session_id: str, concept_ids: list[int]) -> None
write_route_steps(conn, session_id: str, route_version: int, steps: list[dict]) -> None
update_learner_state(conn, session_id: str, concept_id: int, state: dict) -> None
record_quiz_attempt(conn, attempt: dict) -> None
record_decision(conn, decision: dict) -> None
```

- [ ] **Step 6: Verify**

Run: `pytest tests/test_bkt.py tests/test_storage.py -v`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add litnav/state.py litnav/storage tests/test_bkt.py tests/test_storage.py
git commit -m "feat: add M0 state and storage"
```

### Task 3: M0 Deterministic Flow and Gate

**Files:**
- Create: `litnav/retrieval/fake.py`
- Create: `litnav/graph/router.py`
- Create: `litnav/graph/builder.py`
- Create: `litnav/evaluation/verify_m0.py`
- Create: `tests/test_router.py`
- Create: `tests/test_m0_flow.py`
- Modify: `README.md`

- [ ] **Step 1: Add router tests**

Test `advance`, `diagnose`, `reteach`, and `concede` decisions.

- [ ] **Step 2: Implement `tutor_router`**

Use the decision order:

```text
mastered -> reteach -> diagnose -> concede
```

- [ ] **Step 3: Add fake retrieval**

`get_chunk_for_concept(conn, concept_id: int) -> dict` returns the seed chunk for that concept.

- [ ] **Step 4: Implement `run_m0_session`**

`run_m0_session(conn, answer: str = "embedding vectors") -> dict` must:

1. create a session,
2. initialize learner state,
3. write route steps,
4. retrieve one chunk,
5. select one quiz item,
6. grade the deterministic answer,
7. update learner state,
8. record quiz attempt,
9. record decision,
10. return a summary dict.

- [ ] **Step 5: Implement `verify_m0`**

Expected output:

```text
G0 PASS: session written
G0 PASS: route written
G0 PASS: learner_state updated
G0 PASS: quiz_attempt written
G0 PASS: decision written
G0 PASS: offline run
```

- [ ] **Step 6: Update README**

Once G0 passes, replace the planning-only quick start with:

```bash
pip install -r requirements.txt
python -m litnav.evaluation.verify_m0
```

- [ ] **Step 7: Verify**

Run:

```bash
pytest tests/test_router.py tests/test_m0_flow.py -v
python -m litnav.evaluation.verify_m0
```

Expected: tests pass and all G0 PASS lines print.

- [ ] **Step 8: Commit**

```bash
git add litnav/retrieval litnav/graph litnav/evaluation tests README.md
git commit -m "feat: add M0 verification gate"
```

### Task 4: M1 Route Planning and Replan

**Files:**
- Create: `litnav/nodes/planner.py`
- Create: `litnav/nodes/select_next.py`
- Create: `litnav/nodes/diagnose.py`
- Create: `litnav/nodes/replan.py`
- Create: `litnav/evaluation/verify_m1.py`
- Create: `tests/test_m1_replan.py`
- Modify: `litnav/graph/builder.py`
- Modify: `litnav/storage/repo.py`

- [ ] **Step 1: Add replan tests**

`tests/test_m1_replan.py` must cover:

```text
correct dense retrieval answer -> advance
negative sampling failure -> route_version increments
negative_sampling inserted before contrastive_learning
decision rationale mentions failed quiz and prerequisite edge
```

- [ ] **Step 2: Implement topological planner**

`planner.py` exposes:

```python
plan_route(conn, target_concept_ids: list[int]) -> list[dict]
```

For M1, implement a deterministic topological sort from `concept_edges`.

- [ ] **Step 3: Implement `diagnose_gap`**

`diagnose_gap(state: dict) -> dict` returns the lowest unmet prerequisite for the current concept.

- [ ] **Step 4: Implement `replan`**

`replan_route(state: dict, missing_concept_id: int) -> list[dict]` inserts the missing prerequisite before the blocked concept and increments `route_version`.

- [ ] **Step 5: Extend storage helpers**

Add:

```python
get_route_steps(conn, session_id: str, route_version: int) -> list[dict]
get_latest_route_version(conn, session_id: str) -> int
```

- [ ] **Step 6: Implement `verify_m1`**

Expected output:

```text
G1 PASS: correct answer advances
G1 PASS: prerequisite failure diagnosed
G1 PASS: route_version incremented
G1 PASS: missing prerequisite inserted
G1 PASS: rationale traceable
```

- [ ] **Step 7: Verify**

Run:

```bash
pytest tests/test_m1_replan.py -v
python -m litnav.evaluation.verify_m1
```

- [ ] **Step 8: Commit**

```bash
git add litnav/nodes litnav/evaluation/verify_m1.py litnav/graph/builder.py litnav/storage/repo.py tests/test_m1_replan.py
git commit -m "feat: add M1 adaptive route planning"
```

### Task 5: M1 Thin Recordable App

**Files:**
- Create: `litnav/app.py`
- Modify: `README.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: Add CLI app command**

`litnav/app.py` supports:

```bash
python -m litnav.app demo-m1 --answer wrong_prereq
python -m litnav.app demo-m1 --answer correct
```

- [ ] **Step 2: Print recordable trace**

The CLI output must include:

```text
Session:
Route before:
Quiz:
Answer:
Decision:
Route after:
Evidence:
```

- [ ] **Step 3: Update demo docs**

Add the exact CLI transcript shape to `docs/demo-script.md`.

- [ ] **Step 4: Verify**

Run:

```bash
python -m litnav.app demo-m1 --answer wrong_prereq
python -m litnav.app demo-m1 --answer correct
```

Expected: wrong path replans; correct path advances.

- [ ] **Step 5: Commit**

```bash
git add litnav/app.py README.md docs/demo-script.md
git commit -m "feat: add M1 recordable demo command"
```

### Task 6: M2 Misconception and Parallel Quiz Data

**Files:**
- Create: `data/seed/rag_m2_demo.json`
- Modify: `litnav/storage/schema.py`
- Modify: `litnav/storage/seed.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Extend schema**

Add:

```text
misconceptions
tutor_turns
```

Use the DDL in `docs/data-contract.md`.

- [ ] **Step 2: Add M2 fixture**

`rag_m2_demo.json` must include:

```text
misconception id: dr_is_keyword_match
wrong_model: dense retrieval is keyword matching
correct_model: dense retrieval compares embeddings
reteach_strategy: analogy
two parallel quiz items for dense_retrieval
```

- [ ] **Step 3: Extend seed loader**

`seed_demo_data` accepts `include_m2: bool = False`. When true, load misconceptions and parallel quiz items.

- [ ] **Step 4: Add storage tests**

Assert:

```python
assert conn.execute("select count(*) from misconceptions").fetchone()[0] >= 1
assert conn.execute("select count(*) from tutor_turns").fetchone()[0] == 0
```

- [ ] **Step 5: Verify**

Run: `pytest tests/test_storage.py -v`

- [ ] **Step 6: Commit**

```bash
git add data/seed/rag_m2_demo.json litnav/storage tests/test_storage.py
git commit -m "feat: add M2 tutor data contract"
```

### Task 7: M2 Teach, Check, Grade, Reteach, Concede

**Files:**
- Create: `litnav/nodes/teach.py`
- Create: `litnav/nodes/check.py`
- Create: `litnav/nodes/grade.py`
- Create: `litnav/nodes/reteach.py`
- Create: `litnav/nodes/concede.py`
- Create: `tests/test_m2_tutor.py`
- Create: `litnav/evaluation/verify_m2.py`
- Modify: `litnav/graph/router.py`
- Modify: `litnav/graph/builder.py`
- Modify: `litnav/storage/repo.py`

- [ ] **Step 1: Add M2 tests**

Cover:

```text
teach output cites chunk id
grade detects dr_is_keyword_match
reteach picks analogy after direct explanation
concede fires after MAX_RETEACH when prereqs are met
confidence remains lower than mastery on first observation
```

- [ ] **Step 2: Implement `teach`**

Return:

```python
{
    "concept_id": 1,
    "strategy": "direct",
    "message": "...",
    "cited_chunks": ["c_dense_1"],
}
```

M2 can use deterministic templates. No LLM is required.

- [ ] **Step 3: Implement `check`**

Select parallel quiz items by concept, qtype, and difficulty. Ensure pre/post do not use the same item id in one tutor turn.

- [ ] **Step 4: Implement `grade`**

Detect `dr_is_keyword_match` when an answer contains keyword/BM25 framing for dense retrieval. Update BKT and confidence.

- [ ] **Step 5: Implement `reteach`**

Pick the first strategy not in `tried_strategies` from:

```text
direct
analogy
worked_example
contrast_case
simpler_decomposition
```

- [ ] **Step 6: Implement `concede`**

Write a `concede` decision and advance without another reteach.

- [ ] **Step 7: Implement `verify_m2`**

Expected output:

```text
G2 PASS: teaching cites evidence
G2 PASS: misconception detected
G2 PASS: reteach strategy switched
G2 PASS: concede terminates exhausted loop
G2 PASS: confidence calibrated
```

- [ ] **Step 8: Verify**

Run:

```bash
pytest tests/test_m2_tutor.py -v
python -m litnav.evaluation.verify_m2
```

- [ ] **Step 9: Commit**

```bash
git add litnav/nodes litnav/graph litnav/storage tests/test_m2_tutor.py litnav/evaluation/verify_m2.py
git commit -m "feat: add M2 tutor loop"
```

### Task 8: M2 Demo Command and Documentation

**Files:**
- Modify: `litnav/app.py`
- Modify: `README.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/evaluation.md`

- [ ] **Step 1: Add M2 CLI command**

```bash
python -m litnav.app demo-m2 --answer keyword
python -m litnav.app demo-m2 --answer embedding
python -m litnav.app demo-m2 --answer exhausted
```

- [ ] **Step 2: Print tutor trace**

Output must show:

```text
Strategy before:
Detected misconception:
Strategy after:
Mastery:
Confidence:
Cited chunks:
Decision:
```

- [ ] **Step 3: Update docs**

Mark G2 command as implemented in `docs/evaluation.md` and add the transcript shape to `docs/demo-script.md`.

- [ ] **Step 4: Verify**

Run all three M2 demo commands and `python -m litnav.evaluation.verify_m2`.

- [ ] **Step 5: Commit**

```bash
git add litnav/app.py README.md docs/demo-script.md docs/evaluation.md
git commit -m "feat: add M2 recordable tutor demo"
```

### Task 9: M3 Induced Scaffold Data and Confidence

**Files:**
- Create: `data/seed/rag_m3_induction.json`
- Create: `litnav/nodes/induce.py`
- Create: `tests/test_m3_induction.py`
- Modify: `litnav/storage/schema.py`
- Modify: `litnav/storage/seed.py`
- Modify: `litnav/storage/repo.py`

- [ ] **Step 1: Add induction table**

Add `induction_log` using `docs/data-contract.md`.

- [ ] **Step 2: Add M3 fixture**

Include off-skeleton concept:

```text
hard_negative_mining
```

Include evidence chunks supporting:

```text
negative_sampling -> hard_negative_mining
misconception: more negatives is always better
correct model: hard negatives matter more than raw count
```

- [ ] **Step 3: Implement confidence helper**

`induced_confidence(n_chunks: int, max_strength: str, multi_paper: bool) -> float`

Use:

```python
strength_bonus = {"weak_hint": 0.05, "general_statement": 0.15, "explicit_assertion": 0.25}[max_strength]
multi_paper_bonus = 0.10 if multi_paper else 0.0
return round(min(0.95, 0.35 + 0.15 * n_chunks + strength_bonus + multi_paper_bonus), 2)
```

- [ ] **Step 4: Implement `induce_scaffold`**

Return and persist:

```python
{
    "kind": "prereq",
    "source": "induced",
    "edge": {"prereq_concept": "negative_sampling", "target_concept": "hard_negative_mining"},
    "evidence_chunks": ["c_hnm_1"],
    "confidence": 0.75,
    "confidence_basis": {"n_chunks": 1, "max_strength": "explicit_assertion", "multi_paper": false}
}
```

- [ ] **Step 5: Add tests**

Assert:

```text
source is induced
evidence_chunks is non-empty
confidence_basis has n_chunks, max_strength, multi_paper
induction_log row is written
```

- [ ] **Step 6: Verify**

Run: `pytest tests/test_m3_induction.py -v`

- [ ] **Step 7: Commit**

```bash
git add data/seed/rag_m3_induction.json litnav/nodes/induce.py litnav/storage tests/test_m3_induction.py
git commit -m "feat: add M3 induced scaffold core"
```

### Task 10: M3 Off-Skeleton Routing and Gate

**Files:**
- Create: `litnav/evaluation/verify_m3.py`
- Modify: `litnav/nodes/select_next.py`
- Modify: `litnav/graph/builder.py`
- Modify: `litnav/app.py`
- Modify: `docs/evaluation.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: Detect off-skeleton concept**

`select_next_concept` returns decision `induce` when the requested concept slug is not in the curated DAG.

- [ ] **Step 2: Route through `induce_scaffold`**

After induction, write the induced concept/edge/misconception and continue to retrieve/teach.

- [ ] **Step 3: Implement `verify_m3`**

Expected output:

```text
G3 PASS: off-skeleton concept detected
G3 PASS: induced edge written
G3 PASS: induced misconception written
G3 PASS: confidence_basis written
G3 PASS: induced scaffold used in route
```

- [ ] **Step 4: Add M3 demo command**

```bash
python -m litnav.app demo-m3 --concept hard_negative_mining
```

Output must show:

```text
Off-skeleton concept:
Induced prerequisite:
Induced misconception:
Evidence:
Confidence basis:
Route insertion:
```

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_m3_induction.py -v
python -m litnav.evaluation.verify_m3
python -m litnav.app demo-m3 --concept hard_negative_mining
```

- [ ] **Step 6: Commit**

```bash
git add litnav/evaluation/verify_m3.py litnav/nodes litnav/graph litnav/app.py docs/evaluation.md docs/demo-script.md
git commit -m "feat: add M3 induction gate"
```

### Task 11: M4 Trace UI and Judge-Facing Polish

**Files:**
- Create: `litnav/ui/__init__.py`
- Create: `litnav/ui/server.py`
- Create: `litnav/ui/templates/index.html`
- Create: `tests/test_ui_trace.py`
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: Add lightweight UI dependency**

If a browser UI is chosen, add:

```text
fastapi>=0.115
uvicorn>=0.30
jinja2>=3.1
```

If time is short, keep CLI as the official demo UI and skip this task.

- [ ] **Step 2: Add trace endpoint**

`GET /sessions/{session_id}/trace` returns:

```json
{
  "route": [],
  "learner_state": {},
  "decisions": [],
  "evidence": [],
  "provenance": []
}
```

- [ ] **Step 3: Add dashboard**

The dashboard must show:

```text
left: teaching transcript
middle: route and route_version
right: evidence, decision rationale, mastery/confidence, curated/induced provenance
```

- [ ] **Step 4: Add UI test**

`tests/test_ui_trace.py` asserts the trace endpoint includes route, decisions, and evidence for a seeded session.

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_ui_trace.py -v
python -m litnav.evaluation.verify_m3
```

- [ ] **Step 6: Commit**

```bash
git add litnav/ui requirements.txt tests/test_ui_trace.py README.md docs/demo-script.md
git commit -m "feat: add trace UI"
```

### Task 12: Final Competition Freeze

**Files:**
- Modify: `README.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/evaluation.md`
- Modify: `docs/milestones.md`

- [ ] **Step 1: Run all implemented gates**

Run:

```bash
pytest -v
python -m litnav.evaluation.verify_m0
python -m litnav.evaluation.verify_m1
python -m litnav.evaluation.verify_m2
python -m litnav.evaluation.verify_m3
```

If M4 UI exists, run its UI test as part of `pytest`.

- [ ] **Step 2: Record highest stable demo**

Record the highest stable demo command:

```bash
python -m litnav.app demo-m3 --concept hard_negative_mining
```

If M3 fails, record:

```bash
python -m litnav.app demo-m2 --answer keyword
```

If M2 fails, record:

```bash
python -m litnav.app demo-m1 --answer wrong_prereq
```

- [ ] **Step 3: Update docs with actual stable phase**

Set README current progress to the highest passing milestone and update `docs/demo-script.md` with the exact command used for recording.

- [ ] **Step 4: Tag stable snapshot**

```bash
git tag stable-m3-demo
```

Use `stable-m2-demo` or `stable-m1-demo` if the higher gate did not pass.

- [ ] **Step 5: Commit final docs**

```bash
git add README.md docs/demo-script.md docs/evaluation.md docs/milestones.md
git commit -m "docs: freeze competition demo instructions"
```

## Gate Summary

| Milestone | Required command | Passing evidence |
|---|---|---|
| M0 | `python -m litnav.evaluation.verify_m0` | session, route, learner_state, quiz_attempt, decision, offline run |
| M1 | `python -m litnav.evaluation.verify_m1` | route_version changes on prerequisite gap |
| M2 | `python -m litnav.evaluation.verify_m2` | cited teaching, misconception, switched strategy, concede, confidence calibration |
| M3 | `python -m litnav.evaluation.verify_m3` | induced edge/misconception, evidence, confidence_basis, route use |
| M4 | `pytest tests/test_ui_trace.py -v` | trace UI exposes route, decisions, evidence |

## Self-Review

- Spec coverage: M0-M4 are represented with files, tasks, tests, and gate commands.
- M0 detail: The existing `2026-06-16-m0-walking-skeleton.md` remains the more detailed M0 task list.
- M1-M3 detail: This plan defines concrete node files, evaluation scripts, fixture files, and expected outputs.
- Placeholder scan: No task uses "TBD" or depends on undefined external services.
- Scope control: Live paper ingestion, vector retrieval, and polished UI are delayed until the deterministic gates pass.

Plan complete and saved to `docs/superpowers/plans/2026-06-16-complete-engineering-plan.md`.
