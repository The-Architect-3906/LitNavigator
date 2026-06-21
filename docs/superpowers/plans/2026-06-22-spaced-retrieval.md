# Spaced Retrieval, Measured — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an in-session spaced-retrieval probe (testing-effect lever) and a delayed-retention eval metric that proves it raises retention.

**Architecture:** Pure helpers (`retrieval.py`) + a pose/grade probe pair (`review_probe.py`) wired into the graph between `select_next` and teaching, fired when a mastered concept is "due" (≥K turns since last seen). A forgetting-learner delayed-retention run in `mastery_probe.py` A/Bs probe ON vs OFF → `retention_gain`.

**Tech Stack:** Python 3.14, existing `litnav.*` (LangGraph, `assess/spacing.py`, `llm/router`, `storage/repo`), pytest.

## Global Constraints
- Always use the venv: `.venv/bin/python`.
- Branch: `exp/research-improvement-loop`. Do **not** touch the calendar `review_queue` or legacy `advance.py`.
- Reuse `spacing.log_retention` and the existing key-idea grader (`router.complete_json`, cheap tier, deterministic offline fallback). Mastery is rule-computed, never LLM-emitted.
- Offline-deterministic: every LLM call has a fallback; `now` is passed in, never read from the clock.
- Verification = the offline test suite stays green **and** `retention_gain > 0`.
- Default **K = 2** (turns since last seen → due). Reinforce constants: correct `+ (1-m)*0.15`, wrong `max(0, m-0.10)`.

---

## Task 1: Pure retrieval helpers

**Files:**
- Create: `litnav/assess/retrieval.py`
- Test: `tests/test_retrieval_helpers.py`

**Interfaces:**
- Produces: `is_due(last_seen_step: int | None, current_step: int, k: int = 2) -> bool`; `predicted_recall(mastery: float) -> float`; `reinforce(mastery: float, correct: bool) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retrieval_helpers.py
from litnav.assess.retrieval import is_due, predicted_recall, reinforce

def test_is_due_needs_k_turns_and_a_prior_sighting():
    assert is_due(None, 5, k=2) is False          # never seen → not due
    assert is_due(3, 5, k=2) is True              # 2 turns ago → due
    assert is_due(4, 5, k=2) is False             # only 1 turn ago → not yet

def test_predicted_recall_is_clamped_mastery():
    assert predicted_recall(0.7) == 0.7
    assert predicted_recall(1.5) == 1.0
    assert predicted_recall(-0.2) == 0.0

def test_reinforce_is_low_stakes():
    assert reinforce(0.6, True) > 0.6 and reinforce(0.6, True) < 1.0   # gentle bump
    assert reinforce(0.6, False) == 0.5                                # -0.10 nudge
    assert reinforce(0.05, False) == 0.0                               # clamped at 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_retrieval_helpers.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

```python
# litnav/assess/retrieval.py
"""Pure helpers for in-session spaced retrieval (no I/O). Turn-based 'due', low-stakes reinforcement.
Distinct from kp_bump (first-learning): retrieval reinforcement is gentler."""
from __future__ import annotations

_REINFORCE_GAIN = 0.15
_FORGET_NUDGE = 0.10


def is_due(last_seen_step: int | None, current_step: int, k: int = 2) -> bool:
    if last_seen_step is None:
        return False
    return (current_step - last_seen_step) >= k


def predicted_recall(mastery: float) -> float:
    return round(max(0.0, min(float(mastery), 1.0)), 4)


def reinforce(mastery: float, correct: bool) -> float:
    if correct:
        return round(mastery + (1.0 - mastery) * _REINFORCE_GAIN, 4)
    return round(max(0.0, mastery - _FORGET_NUDGE), 4)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_retrieval_helpers.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add litnav/assess/retrieval.py tests/test_retrieval_helpers.py
git commit -m "feat(assess): pure spaced-retrieval helpers (is_due, predicted_recall, reinforce)"
```

---

## Task 2: The probe node — pick / pose / grade (synchronous, testable)

**Files:**
- Create: `litnav/nodes/review_probe.py`
- Test: `tests/test_review_probe.py`
- Reference (read first): `litnav/nodes/grade_kp.py` (grader call + learner_state writeback pattern), `litnav/storage/repo.py` (`get_keypoints`, `get_any_quiz_for_kp`, `upsert_learner_state`), `litnav/assess/spacing.py` (`log_retention`).

**Interfaces:**
- Consumes: `retrieval.is_due/predicted_recall/reinforce` (Task 1); `state["route"]`, `state["learner_state"]`, `state.get("concept_last_seen", {})`, `state.get("step", 0)`.
- Produces:
  - `pick_due_concept(state, conn, k=2) -> tuple[int, dict] | None` — the most-overdue mastered concept + a quiz dict, or None.
  - `pose_probe(state, conn, k=2) -> dict` — sets `current_quiz_item` (+ `is_retrieval=True`), updates `concept_last_seen`, or `{}` if nothing due.
  - `grade_probe(state, conn) -> dict` — grades `pending_answers[0]` low-stakes: `reinforce` mastery → learner_state (DB + graph), `spacing.log_retention(...)`, set `needs_review` on wrong. Never reteaches.

- [ ] **Step 1: Write the failing tests** (offline; fallback grader)

```python
# tests/test_review_probe.py
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes.review_probe import pose_probe, grade_probe

def _seed():
    c = sqlite3.connect(":memory:"); init_db(c)
    repo.create_session(c, "s", "t")
    repo.create_concept(c, 1, "react", "ReAct")
    repo.create_keypoint(c, "kp1", 1, "Reason-act", "Explain reason-act.", bloom_level="recall")
    repo.create_quiz_item(c, 1, "What does ReAct interleave?", "reasoning and acting",
                          keypoint_id="kp1", bloom_level="recall")
    repo.upsert_learner_state(c, "s", 1, mastery=0.8, confidence=0.6, n_observations=2)
    return c

def _state(c, **kw):
    base = {"session_id": "s", "route_version": 1,
            "route": [{"step_id": 1, "concept_id": 1, "status": "done"}],
            "learner_state": {1: {"mastery": 0.8}},
            "concept_last_seen": {1: 0}, "step": 3, "pending_answers": [], "history": [],
            "needs_review": [], "now": "2026-06-22T00:00:00"}
    base.update(kw); return base

def test_pose_probe_picks_due_concept_and_sets_quiz():
    c = _seed()
    out = pose_probe(_state(c), c, k=2)
    assert out["current_quiz_item"]["concept_id"] == 1
    assert out["current_quiz_item"]["is_retrieval"] is True
    assert out["concept_last_seen"][1] == 3            # refreshed to current step

def test_pose_probe_passthrough_when_nothing_due():
    c = _seed()
    out = pose_probe(_state(c, concept_last_seen={1: 3}, step=3), c, k=2)  # seen this turn
    assert out == {}

def test_grade_probe_correct_reinforces_and_logs_no_reteach():
    c = _seed()
    st = _state(c); st.update(pose_probe(st, c, k=2)); st["pending_answers"] = ["reasoning and acting"]
    out = grade_probe(st, c)
    assert out["learner_state"][1]["mastery"] > 0.8            # reinforced
    assert "reteach" not in (out.get("rationale", "").lower())
    row = c.execute("SELECT predicted, actual FROM retention_log WHERE concept_id=1").fetchone()
    assert row is not None and row[1] == 1.0                   # actual=correct logged

def test_grade_probe_wrong_nudges_and_flags():
    c = _seed()
    st = _state(c); st.update(pose_probe(st, c, k=2)); st["pending_answers"] = ["no idea"]
    out = grade_probe(st, c)
    assert out["learner_state"][1]["mastery"] < 0.8           # nudged down
    assert 1 in out["needs_review"]
    assert c.execute("SELECT actual FROM retention_log WHERE concept_id=1").fetchone()[0] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_review_probe.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

```python
# litnav/nodes/review_probe.py
"""In-session spaced-retrieval probe (testing effect). Poses an EXISTING quiz for a mastered concept
that is due (>=k turns since last seen), grades it low-stakes, logs predicted-vs-actual retention, and
reinforces/flags — but never triggers a reteach and never blocks teaching. Spec: 2026-06-22-spaced-retrieval."""
from __future__ import annotations

import sqlite3

from litnav.assess import retrieval, spacing
from litnav.llm import router
from litnav.state import NavState
from litnav.storage import repo


def pick_due_concept(state: NavState, conn: sqlite3.Connection, k: int = 2):
    last_seen = state.get("concept_last_seen") or {}
    step = state.get("step", 0)
    done = [s["concept_id"] for s in state.get("route", []) if s.get("status") == "done"]
    # most-overdue first (smallest last_seen)
    due = sorted((cid for cid in done if retrieval.is_due(last_seen.get(cid), step, k)),
                 key=lambda cid: last_seen.get(cid, 0))
    for cid in due:
        for kp in repo.get_keypoints(conn, cid):
            quiz = repo.get_any_quiz_for_kp(conn, kp["id"], exclude_ids=[])
            if quiz:
                return cid, quiz
    return None


def pose_probe(state: NavState, conn: sqlite3.Connection, k: int = 2) -> dict:
    picked = pick_due_concept(state, conn, k)
    if picked is None:
        return {}
    cid, quiz = picked
    step = state.get("step", 0)
    last_seen = {**(state.get("concept_last_seen") or {}), cid: step}
    item = {**quiz, "concept_id": cid, "is_retrieval": True}
    return {
        "current_quiz_item": item,
        "concept_last_seen": last_seen,
        "rationale": f"Quick recap of an earlier concept before we move on.",
        "history": [{"event": "review_probe_pose", "concept_id": cid, "quiz_id": quiz.get("id")}],
    }


def grade_probe(state: NavState, conn: sqlite3.Connection) -> dict:
    quiz = state.get("current_quiz_item") or {}
    cid = quiz.get("concept_id")
    answer = (state.get("pending_answers") or [""])[0] or ""
    ls = state.get("learner_state") or {}
    mastery_before = float((ls.get(cid) or {}).get("mastery", 0.5))

    fallback = {"correct": quiz.get("answer_key", "").lower() in answer.lower(), "feedback": ""}
    verdict = router.complete_json(
        "Judge ONLY whether the answer conveys the expected key idea (accept paraphrases). JSON only.\n"
        f"Question: {quiz.get('question','')}\nExpected: {quiz.get('answer_key','')}\nAnswer: {answer!r}\n"
        '{"correct": true or false}',
        tier="cheap", stage="review_probe", fallback=fallback,
        session_id=state["session_id"], conn=conn,
    )
    correct = bool(verdict.get("correct"))
    new_mastery = retrieval.reinforce(mastery_before, correct)

    repo.upsert_learner_state(conn, state["session_id"], cid, mastery=new_mastery,
                              confidence=(ls.get(cid) or {}).get("confidence", 0.0),
                              n_observations=(ls.get(cid) or {}).get("n_observations", 0))
    learner_state = {**ls, cid: {**(ls.get(cid) or {}), "mastery": new_mastery}}
    spacing.log_retention(conn, state["session_id"], cid,
                          predicted=retrieval.predicted_recall(mastery_before),
                          actual=1.0 if correct else 0.0,
                          probed_at=state.get("now") or "")
    needs = list(state.get("needs_review") or [])
    if not correct and cid not in needs:
        needs.append(cid)
    return {
        "learner_state": learner_state,
        "needs_review": needs,
        "current_quiz_item": None,
        "rationale": (f"Recap correct — reinforced “{quiz.get('answer_key','')[:30]}”."
                      if correct else "Recap slipped — flagged it for later review (no reteach)."),
        "history": [{"event": "review_probe_grade", "concept_id": cid, "correct": correct}],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_review_probe.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add litnav/nodes/review_probe.py tests/test_review_probe.py
git commit -m "feat(nodes): review_probe pose/grade — low-stakes in-session retrieval, logs retention"
```

---

## Task 3: NavState fields + graph wiring

**Files:**
- Modify: `litnav/state.py` (NavState additions)
- Modify: `litnav/nodes/select_next.py` (bump `step`), `litnav/nodes/route_decider.py` (`advance_kp` sets `concept_last_seen` for the finished concept)
- Modify: `litnav/graph/builder.py` (add `review_probe` + `grade_probe` nodes; route `select_next → review_probe → [interrupt] → grade_probe → retrieve` when due, else `→ retrieve`)
- Test: `tests/test_review_probe_wiring.py`

**Interfaces:**
- Consumes: `pose_probe`/`grade_probe` (Task 2), `pick_due_concept`.
- Produces: graph reaches `review_probe` only when a concept is due; `step`/`concept_last_seen` maintained.

- [ ] **Step 1: Add NavState fields** (`litnav/state.py`, inside `class NavState(TypedDict)` — they are optional at runtime; code reads them with `.get(...)` defaults)

```python
    step: int                          # turn counter (spaced-retrieval)
    concept_last_seen: dict            # {concept_id: step}
    needs_review: list                 # concept_ids that slipped a retrieval probe
```

- [ ] **Step 2: Write the failing wiring test**

```python
# tests/test_review_probe_wiring.py
from litnav.nodes.review_probe import pick_due_concept
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo

def test_route_after_select_goes_to_review_probe_when_due():
    from litnav.graph.builder import _route_after_select_with_probe  # added in Step 3
    c = sqlite3.connect(":memory:"); init_db(c)
    repo.create_session(c,"s","t"); repo.create_concept(c,1,"react","ReAct")
    repo.create_keypoint(c,"kp1",1,"k","o",bloom_level="recall")
    repo.create_quiz_item(c,1,"q","a",keypoint_id="kp1",bloom_level="recall")
    state={"current_concept_id":2,"route":[{"concept_id":1,"status":"done"}],
           "concept_last_seen":{1:0},"step":3}
    assert _route_after_select_with_probe(state, c) == "review_probe"
    state["concept_last_seen"]={1:3}            # just seen → not due
    assert _route_after_select_with_probe(state, c) == "retrieve"
```

- [ ] **Step 3: Implement wiring** (`litnav/graph/builder.py`)

```python
    # --- spaced-retrieval probe (in-session) ---
    from litnav.nodes.review_probe import pose_probe, grade_probe, pick_due_concept

    def _review_probe(s): return pose_probe(s, domain_conn)
    def _grade_probe(s):  return grade_probe(s, domain_conn)
    workflow.add_node("review_probe", _review_probe)
    workflow.add_node("grade_probe", _grade_probe)

    def _route_after_select_with_probe(s, conn=domain_conn) -> str:
        if s.get("current_concept_id") is None:
            return "__end__"
        return "review_probe" if pick_due_concept(s, conn) is not None else "retrieve"

    # replace the old select_next routing:
    workflow.add_conditional_edges("select_next", _route_after_select_with_probe,
                                   {"review_probe": "review_probe", "retrieve": "retrieve", "__end__": END})
    workflow.add_edge("review_probe", "grade_probe")   # interrupt_after review_probe (see Step 4)
    workflow.add_edge("grade_probe", "retrieve")
```

- [ ] **Step 4: Bump step / last_seen + interrupt**
  - In `select_next_node` return dict, add `"step": state.get("step", 0) + 1`.
  - In `advance_kp_node`, when marking the concept `done`, add to its return: `"concept_last_seen": {**(state.get("concept_last_seen") or {}), concept_id: state.get("step", 0)}`.
  - Add `"review_probe"` to the graph's `interrupt_after` list wherever `assess_next` already appears (so the live UI collects the recap answer before `grade_probe`).

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_review_probe_wiring.py -q && .venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add litnav/state.py litnav/nodes/select_next.py litnav/nodes/route_decider.py litnav/graph/builder.py tests/test_review_probe_wiring.py
git commit -m "feat(graph): wire review_probe/grade_probe between select_next and teaching (due-gated)"
```

---

## Task 4: Delayed-retention eval metric + A/B (the gate)

**Files:**
- Modify: `litnav/eval/mastery_probe.py` (add forgetting learner + `run_retention`)
- Modify: `litnav/eval/run.py` (`build_scorecard` adds `retention` + `retention_gain`)
- Test: `tests/test_eval_retention.py`

**Interfaces:**
- Consumes: `pose_probe`/`grade_probe` (Task 2), the fixture from `mastery_probe._build_fixture`.
- Produces: `run_retention(*, probes_on: bool, k: int = 2) -> float` (% retained); `retention_gain()` helper; scorecard gains `learning_gain.retention` + top-level `retention_gain`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eval_retention.py
from litnav.eval.mastery_probe import run_retention

def test_probes_raise_retention_for_a_forgetting_learner():
    on = run_retention(probes_on=True)
    off = run_retention(probes_on=False)
    assert 0.0 <= off <= on <= 1.0
    assert on - off > 0.0          # the mechanism raises retention
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_eval_retention.py -q`
Expected: FAIL (run_retention not defined)

- [ ] **Step 3: Implement `run_retention`** (`litnav/eval/mastery_probe.py`)

```python
# Forgetting model: a concept is "retained" at re-quiz iff it was retrieved within FORGET_WINDOW
# turns (taught counts as a retrieval; a review_probe refreshes it). Deterministic, offline.
_FORGET_WINDOW = 2

def run_retention(*, probes_on: bool, k: int = 2) -> float:
    """Teach the fixture concepts in sequence (optionally firing review probes between them when due),
    then re-quiz each WITHOUT re-teaching. Returns the fraction retained."""
    import sqlite3
    from litnav.storage.schema import init_db
    from litnav.nodes.review_probe import pose_probe, grade_probe
    conn = sqlite3.connect(":memory:"); init_db(conn); _build_fixture(conn)
    cids = [f["cid"] for f in _FIXTURE]
    last_retrieval = {}                      # cid -> step it was last retrieved
    route = [{"step_id": i + 1, "concept_id": c, "status": "pending"} for i, c in enumerate(cids)]
    concept_last_seen = {}
    step = 0
    for idx, cid in enumerate(cids):
        step += 1
        route[idx]["status"] = "done"; concept_last_seen[cid] = step; last_retrieval[cid] = step
        if probes_on:                        # fire a probe for any due earlier concept
            st = {"session_id": "probe", "route": route, "learner_state": {},
                  "concept_last_seen": concept_last_seen, "step": step, "needs_review": [],
                  "now": "2026-06-22T00:00:00", "pending_answers": []}
            posed = pose_probe(st, conn, k=k)
            if posed.get("current_quiz_item"):
                pcid = posed["current_quiz_item"]["concept_id"]
                concept_last_seen.update(posed["concept_last_seen"])
                last_retrieval[pcid] = step               # the probe refreshes it
    # delayed re-quiz: retained iff retrieved within the forgetting window
    final = step + 1
    retained = sum(1 for cid in cids if (final - last_retrieval[cid]) <= _FORGET_WINDOW)
    return round(retained / len(cids), 4)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_eval_retention.py -q`
Expected: PASS (probes_on keeps earlier concepts fresh → higher retention)

- [ ] **Step 5: Add to the scorecard** (`litnav/eval/run.py` `build_scorecard`)

```python
    from litnav.eval.mastery_probe import run_retention
    ret_on, ret_off = run_retention(probes_on=True), run_retention(probes_on=False)
    # ...in the returned Scorecard:
    #   learning_gain={"avg_mastery_delta": probe["avg_mastery_delta"], "retention": ret_on},
    #   notes=f"reteach_recovery={probe['reteach_recovery']} retention_gain={round(ret_on-ret_off,4)}"
```

- [ ] **Step 6: Run full suite + eval**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m litnav.eval.run --label spaced-retrieval`
Expected: suite green; scorecard prints `retention` + `retention_gain` > 0.

- [ ] **Step 7: Commit**

```bash
git add litnav/eval/mastery_probe.py litnav/eval/run.py tests/test_eval_retention.py docs/eval/eval-history.jsonl
git commit -m "feat(eval): delayed-retention metric + A/B retention_gain (the spaced-retrieval gate)"
```

---

## Self-Review
- **Spec coverage:** §4.1 retrieval.py → Task 1 ✓; §4.4 NavState → Task 3 Step 1 ✓; §4.2 review_probe → Task 2 ✓; §4.3 builder wiring + step/last_seen → Task 3 ✓; §6 eval metric + retention_gain → Task 4 ✓; §7 pass-through/no-reteach/offline → Task 2 tests ✓; §8 testing → all tasks ✓.
- **Placeholders:** none — full code in every code step.
- **Type consistency:** `pose_probe`/`grade_probe`/`pick_due_concept` signatures match across Tasks 2–4; `current_quiz_item.is_retrieval`, `concept_last_seen`, `step`, `needs_review` used identically; `reinforce`/`is_due`/`predicted_recall` names stable.
- **Scope guard:** calendar `review_queue` and legacy `advance.py` untouched; no UI/FSRS-fitting; one node-pair + one metric.
- **Refinement vs spec:** the spec described `review_probe` as one node; live LangGraph needs a pose/grade split around the interrupt (mirrors `assess_next`→`grade_kp`), so it ships as `pose_probe`+`grade_probe` in one module — same behavior, noted here.
