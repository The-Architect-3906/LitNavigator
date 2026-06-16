# LitNavigator Complete Engineering Implementation Plan

> **⚠️ ARCHIVED / HISTORICAL — superseded by the current README roadmap, `docs/milestones.md`, and `docs/engineering-slices.md`.**
> This was the original task-by-task construction plan. **M0–M3 are now implemented and green** (`verify_m0/m1/m2/m3`). The unchecked `[ ]` boxes and the M2/M3 fixture names below (`rag_m2_demo.json` / `rag_m3_induction.json`) are out of date — the project pivoted to the **agent corpus** (`data/seed/agents_m2.json`, `agents_m3.json`, off-skeleton concept `multi_agent_debate`). Use the live docs above for current state; keep this file only for historical context.

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
- `litnav/llm/client.py`: LLM provider abstraction (`qwen` via OpenAI-compatible API; `none` returns the deterministic fixture path). Used by `grade` (M2) and `induce` (M3).
- `litnav/graph/router.py`: `tutor_router` and route decision constants.
- `litnav/graph/builder.py`: state-machine composition — procedural for M0, real LangGraph `StateGraph` + `SqliteSaver` checkpointer from M1.
- `litnav/ui/server.py` + `litnav/ui/templates/`: thin FastAPI/Jinja trace panel, started at M1 and extended each milestone.
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

## Dependency & Parallelization

This plan is written as a serial task list, but the work is meant to run on **three parallel tracks** owned by three people. The gates are serial; the tracks inside each milestone are parallel.

### Tracks (run in parallel for the whole project)

- **Track A — Data/content:** seed fixtures (M0/M2/M3), concept skeleton + `targets`, parallel quiz forms, offline-prerun induction candidates, and the LLM few-shot prompts for `grade` and `induce`.
- **Track B — Engine:** `state.py` (BKT/confidence), storage (schema/seed/repo), `router`, the LangGraph `builder`, the node functions, `llm/client`, and retrieval.
- **Track C — UI + evaluation:** the thin FastAPI GUI, the `verify_m0..m3` gates, the pytest suite, recording scripts, and token/cost accounting.

### Dependency layers (arrows = hard dependency; same layer = parallel)

```text
Layer 0  (start immediately, in parallel — interfaces are frozen in docs/data-contract.md):
  A: data/seed/rag_demo.json (M0 fixture)
  B: litnav/state.py  (bkt_update / confidence_update / initial_concept_state)
  B: litnav/storage/{schema,seed,repo}.py
  C: tests/test_bkt.py, tests/test_storage.py  (tests-first, against the agreed signatures)
        |  all of the above converge
        v
  ===== G0 gate (M0) =====  (must pass before M1)
        v
Layer M1 (after G0):
  B: graph/builder.py (real LangGraph StateGraph + SqliteSaver) + planner(target-only) + diagnose + replan + FTS5 (optional)
  B: llm/client.py    (independent infra — build during M1 so M2/M3 are never blocked on it)
  A: M1 fixture fields (targets / evaluation concept / evidence-bound quiz)
  C: thin FastAPI panel (depends only on the M0 schema, so it runs in PARALLEL with B's M1 logic) + verify_m1
        v  ===== G1 gate =====
Layer M2 (after G1):
  A: M2 fixture (misconception + parallel quiz) + grade few-shot prompt
  B: teach / check / grade(deterministic + LLM) / reteach / concede / four-path router
  C: GUI increment (three-color graph + reteach trail) + verify_m2
        v  ===== G2 gate =====
Layer M3 (after G2):
  A: M3 induction fixture + offline-prerun candidates + induce few-shot prompt
  B: induce (LLM extraction + fixture fallback) + induced_confidence + off-skeleton detection + route insertion
  C: GUI increment (curated/induced distinction + confidence_basis) + verify_m3
        v  ===== G3 gate =====
Layer M4 (after G3): polish, fully parallel.
```

### Parallel/dependency rules

1. **Gates are serial, tracks are parallel.** `G0 → M1 → G1 → M2 → G2 → M3 → G3` must not be skipped, but inside each milestone A/B/C run concurrently and converge at the gate.
2. **The GUI depends only on the schema.** Track C's panel reads the SQLite domain tables, so once the M0 schema is frozen it can be built without waiting for B's per-milestone logic — each gate just adds a panel.
3. **Tests-first decouples C from B.** The `verify_*` scripts and pytest are written against the function signatures defined in `docs/data-contract.md` and this plan, so C does not wait for B to finish implementing.
4. **The LLM client is independent infra.** Build `llm/client.py` during M1 so the M2/M3 LLM paths are never blocked on it.
5. **Track B internal order:** `state → storage → router → builder(graph) → nodes`. But `teach`/`check`/`grade`/`reteach` are sibling nodes — once the graph skeleton exists they can be split across people.
6. **Data does not block the engine.** Fixture shapes are frozen in `docs/data-contract.md`, so Track B depends on the *agreed shape*, not on Track A finishing the content.

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

Use the exact fixture in the M0 plan (`docs/superpowers/plans/2026-06-16-m0-walking-skeleton.md`, Task 1): a `targets` list plus five concepts (incl. `evaluation`), four edges, two papers, five chunks, and five quiz items. `negative_sampling` is a prereq edge but **not** a target.

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
assert conn.execute("select count(*) from concepts").fetchone()[0] == 5
assert conn.execute("select count(*) from concept_edges").fetchone()[0] == 4
assert conn.execute("select count(*) from paper_chunks").fetchone()[0] == 5
assert conn.execute("select count(*) from quiz_items").fetchone()[0] == 5
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

- [ ] **Step 2: Implement topological planner (target-only)**

`planner.py` exposes:

```python
plan_route(conn, target_concept_ids: list[int]) -> list[dict]
```

Sequence **only the `target` concepts** by a deterministic topological sort, breaking ties by ascending `concept.id`. **Do not expand the full prerequisite closure into the initial route** — prerequisites that are not targets (e.g. `negative_sampling`) are assumed mastered and only inserted by `replan` when a quiz reveals a gap. This is exactly what makes the M1 reroute money shot possible: if the planner pre-included `negative_sampling`, there would be nothing left for `replan` to insert.

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

- [ ] **Step 5b: Build the real LangGraph `StateGraph` (M1 replaces the M0 procedural flow)**

Add `langgraph>=0.2` to `requirements.txt`. In `litnav/graph/builder.py`, compose a `StateGraph` whose nodes are the spec §2.2 nodes (`init_or_load_state`, `planner`, `select_next_concept`, `retrieve_evidence`, `grade`, `diagnose_gap`, `replan`, `advance`) and whose conditional edges are driven by `tutor_router`. Persist `NavState` with LangGraph's `SqliteSaver` checkpointer (the audit domain tables are still written via the storage helpers). Add `tests/test_graph_build.py` asserting the graph compiles and runs one correct→advance and one wrong→replan edge. From M1 on, `verify_m*` drive the compiled graph, not `run_m0_session`.

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

### Task 5: M1 Thin Web Panel (primary recordable artifact)

The money shots are visual, so the recordable artifact is a **thin web panel**, not a CLI transcript. The CLI is kept only as a debug runner.

**Files:**
- Create: `litnav/app.py` (CLI debug runner)
- Create: `litnav/ui/__init__.py`, `litnav/ui/server.py`, `litnav/ui/templates/index.html`
- Modify: `requirements.txt` (add `fastapi>=0.115`, `uvicorn>=0.30`, `jinja2>=3.1`)
- Modify: `README.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: Add the thin panel**

`litnav/ui/server.py` is a FastAPI app that runs a demo session and renders, server-side from SQLite, a **left chat / right route panel**:

```text
left:  teaching/quiz transcript for the session
right: current route + route_version, decision rationale, cited evidence
```

Launch: `python -m litnav.ui.server` (or `uvicorn litnav.ui.server:app`). The page must visibly change `route_version` and insert the prerequisite when the wrong-answer path runs.

- [ ] **Step 2: Keep a CLI debug runner**

`litnav/app.py` supports `demo-m1 --answer {wrong_prereq,correct}` and prints the same trace fields (Session / Route before / Quiz / Answer / Decision / Route after / Evidence). This is for debugging, not the demo.

- [ ] **Step 3: Update demo docs**

Add the panel layout and the recording steps to `docs/demo-script.md`.

- [ ] **Step 4: Verify**

```bash
python -m litnav.app demo-m1 --answer wrong_prereq   # replans
python -m litnav.app demo-m1 --answer correct        # advances
python -m litnav.ui.server                            # panel renders route_version change
```

- [ ] **Step 5: Commit**

```bash
git add litnav/app.py litnav/ui requirements.txt README.md docs/demo-script.md
git commit -m "feat: add M1 thin web panel + CLI debug runner"
```

### Task 5c: LLM Client Infrastructure (build during M1; used by M2/M3)

The LLM client is independent infra. Build it while M1 is in flight so the M2/M3 LLM paths are never blocked on it. M2 (`grade`) and M3 (`induce`) call it when `LITNAV_LLM_PROVIDER=qwen`; with `none` they take the deterministic fixture path, so all gates pass offline.

**Files:**
- Create: `litnav/llm/__init__.py`, `litnav/llm/client.py`
- Create: `tests/test_llm_fallback.py`
- Modify: `requirements.txt`, `.env.example`

- [ ] **Step 1: Add dependency and env**

Add `openai>=1.0` to `requirements.txt` (Qwen via DashScope's OpenAI-compatible endpoint). In `.env.example`, keep `LITNAV_LLM_PROVIDER=none` as default and comment that setting `qwen` + a key enables the live LLM path.

- [ ] **Step 2: Implement the provider abstraction**

`litnav/llm/client.py` exposes a single entry point, e.g.:

```python
def complete_json(prompt: str, *, schema_hint: str, fallback: dict) -> dict
```

When `provider == "none"`, return `fallback` unchanged (deterministic). When `provider == "qwen"`, call the OpenAI-compatible endpoint, parse JSON, and on any error/timeout return `fallback`. The caller (grade/induce) always supplies a deterministic `fallback`, so the system degrades gracefully offline.

- [ ] **Step 3: Test the fallback**

`tests/test_llm_fallback.py` asserts that with `provider=none`, `complete_json` returns the supplied fallback verbatim and makes no network call.

- [ ] **Step 4: Commit**

```bash
git add litnav/llm requirements.txt .env.example tests/test_llm_fallback.py
git commit -m "feat: add LLM provider abstraction with deterministic fallback"
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

`teach` uses deterministic templates — no LLM here (the LLM enters at `grade` misconception detection in Step 4, and at M3 `induce`).

- [ ] **Step 3: Implement `check`**

Select parallel quiz items by concept, qtype, and difficulty. Ensure pre/post do not use the same item id in one tutor turn.

- [ ] **Step 4: Implement `grade` (deterministic + LLM paths)**

Misconception detection has two interchangeable paths returning the **same schema** (`{"detected_misconception": {"concept", "id"}, ...}`):
- `provider=none` (default, gates run on this): deterministic — detect `dr_is_keyword_match` when the answer contains keyword/BM25 framing for dense retrieval.
- `provider=qwen`: call `llm.complete_json(...)` with the concept, the answer, and the candidate misconception library, passing the deterministic result as `fallback`.

Either way, BKT mastery and `confidence` are updated by the transparent functions in `state.py` — the LLM never emits a mastery or confidence number.

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

- [ ] **Step 0: M2 UI increment**

Extend `litnav/ui/server.py` + template: add the three-color concept graph (consensus/contested/open or curated status), the reteach trail (`tried_strategies`), and a dual **mastery / confidence** readout. Add `litnav/ui/server.py` to this task's Files.

- [ ] **Step 1: Add M2 CLI command (debug)**

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

Two interchangeable paths: `provider=none` replays the offline-prerun fixture above; `provider=qwen` calls `llm.complete_json(...)` over the already-ingested chunks to (a) extract the supporting chunk ids and (b) label `max_strength` — then `confidence` is computed by `induced_confidence(...)`, **never returned by the LLM**. The fixture is the `fallback`, so this gate also passes offline. To satisfy the spec's "at least one live induction" rule, run this once with `provider=qwen` during the recording (see `docs/evaluation.md`).

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

- [ ] **Step 3b: M3 UI increment**

Extend the panel to visually distinguish `curated` vs `induced` elements, make each induced edge/misconception's evidence openable, and show `confidence_basis` (n_chunks / max_strength / multi_paper → confidence). Add `litnav/ui/server.py` to this task's Files.

- [ ] **Step 4: Add M3 demo command (debug)**

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

### Task 11: M4 Trace UI Polish (the panel already exists since M1)

The thin web panel and its dependencies (`fastapi`/`uvicorn`/`jinja2`) were created in Task 5 and grew each milestone (M2 three-color graph + reteach trail; M3 curated/induced distinction + `confidence_basis`). M4 is **polish only** — do not rebuild the UI here, and never let M4 work risk the latest stable gate.

**Files:**
- Modify: `litnav/ui/server.py`, `litnav/ui/templates/index.html`
- Create: `tests/test_ui_trace.py`
- Modify: `README.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: Confirm UI baseline**

The panel from Task 5 already renders route/route_version, decisions, evidence, mastery/confidence, and curated-vs-induced provenance. M4 only adds nicer graph rendering, interactivity, and coverage warnings. Skip any item that risks the stable demo.

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
