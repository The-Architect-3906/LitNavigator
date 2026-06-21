# OW-4 — TEACH/ASSESS extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Extend the existing LangGraph inner loop (`orient → teach_kp → assess_next → grade_kp → route`) per spec §6.3: goal elicitation, metered+escalating grading, Bloom-leveled MCQ distractors with a flaw gate + IRT difficulty, FSRS spacing, and a delayed retention probe — live-first.

**Architecture:** EXTEND `main`'s inner-loop nodes (do not rebuild). Route the inner-loop LLM calls through the metered `router` (they currently bypass it). Add `goal_elicit`, distractor/flaw/difficulty helpers, an escalating grader, FSRS `review_queue` usage, and a retention probe. New tables only where needed (retention log). Each capability gets a LIVE gate.

**Tech Stack:** Python, `litnav.nodes.*`, `litnav.graph.builder`, `litnav.state`, `litnav.llm.router` (cheap/frontier/embed), `litnav.storage.{repo,openworld_repo,schema}`, `pytest`. Live gate per `docs/2026-06-20-live-gate-execution-contract.md`. Baseline: **231 passed**.

## Spec §6.3 → task trace (no silent gaps)
| §6.3 requirement | Task |
|---|---|
| goal elicitation node → `learner_goal.goal_type` → Bloom ceiling + pacing | **T2** |
| teach strategy from cheap policy (goal × expertise × KT); reteach metacognitive prompt; anti-over-help | **T6** |
| Bloom-leveled item; distractors via overgenerate-and-rank; SAQUET flaw gate | **T4** |
| difficulty from LLM-simulation/IRT, weaker/cheaper simulator, stored `irt_b` | **T4** |
| grading rubric-based, **uncertainty escalation** (low conf → frontier/human-flag), 0–5 | **T3** |
| FSRS spacing: mastered → `review_queue`; cadence ∝ 1/recall-prob; fast-forward at P≥0.95 | **T5** |
| delayed retention probe (risk B): spaced re-quiz, log predicted-vs-actual | **T5** |
| escalation gate + pedagogical-error-cost routing (deferred from OW-0 §5) | **T3** |
| (foundation) route inner-loop LLM through the metered `router` | **T1** |

---

## Task 1: route the inner loop through the metered router (foundation)

**Files:** `litnav/nodes/assess_next.py`, `litnav/nodes/grade_kp.py`, `litnav/nodes/teach_kp.py`, `litnav/nodes/reteach_kp.py` (whichever call `llm_client.complete_*` directly); Test `tests/test_inner_loop_metered.py`.

The inner-loop nodes call `litnav.llm.client.complete_json/complete_text` directly → not metered, not tier-routed, not escalatable. Route them through `litnav.llm.router` with `stage` ("assess"/"grade"/"teach"/"reteach"), `tier="cheap"`, threading `session_id`+`conn` so every call writes `cost_ledger`. Keep the exact same prompts/fallbacks/return shapes.

- [ ] **Step 1: failing test** — a graded turn with `provider=none` writes `cost_ledger` rows tagged `stage in {assess,grade}` for the session (currently zero rows because the nodes bypass the router). Assert ≥1 ledger row after a grade.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** replace `llm_client.complete_json(...)` calls in the inner-loop nodes with `router.complete_json(prompt, tier="cheap", stage="<assess|grade|teach|reteach>", fallback=..., session_id=state["session_id"], conn=conn)`. The nodes receive `conn`; `session_id` is in `state`. Preserve prompt text, `fallback`, and the parsed return exactly. (assess_next quiz-gen → stage="assess"; grade_kp → stage="grade"; teach_kp/reteach_kp grounded text → stage="teach"/"reteach".)
- [ ] **Step 4:** run new test + `verify_m2`, `verify_m3` (these exercise the inner loop offline — must stay green; offline the router returns the fallback exactly as the direct client did) + `pytest -q`. Report real counts.
- [ ] **Step 5: commit** `feat(ow4): route inner-loop LLM calls through the metered router (assess/grade/teach)`.

---

## Task 2: goal elicitation node

**Files:** Create `litnav/nodes/goal_elicit.py`; Modify `litnav/graph/builder.py`, `litnav/state.py`; Test `tests/test_goal_elicit.py`.

Spec: 1 turn → `learner_goal.goal_type ∈ {mastery, functional, survey}` → sets a Bloom ceiling + pacing.

- [ ] **Step 1: failing test** — `goal_elicit_node(state, conn)` classifies a goal ("I need to be able to build X" → functional; "give me an overview" → survey; "I want to deeply master X" → mastery), calls `openworld_repo.set_goal`, and returns state with `goal_type` + a `bloom_ceiling` (mastery→apply/analyze; functional→apply; survey→understand). Offline = heuristic; live = cheap LLM.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement `goal_elicit_node`: heuristic + `router.complete_json(tier="cheap", stage="goal_elicit", fallback={"goal_type": heuristic})`; map goal_type → `bloom_ceiling` (a cap on `BLOOM_LADDER`) + `pacing` (survey = fewer items/concept, mastery = full ladder). Persist via `openworld_repo.set_goal(session_id, goal_text, goal_type, target_concepts)`. Add `bloom_ceiling`/`goal_type` to `NavState` (TypedDict) + a `_bloom_ceiling(goal_type)` helper in state. Wire `goal_elicit` into `builder.py` as the FIRST node (before orient/planner), conditional: run once per session.
- [ ] **Step 4:** `assess_next` respects `bloom_ceiling` (don't upgrade bloom past the ceiling). Add a test that a `survey` goal caps bloom at `understand`.
- [ ] **Step 5:** run + verify_m1/m2/m3 green (goal_elicit defaults to mastery/full-ladder when no goal set, preserving existing behavior) + `pytest -q`. Report.
- [ ] **Step 6: commit** `feat(ow4): goal elicitation node → goal_type + Bloom ceiling/pacing`.

---

## Task 3: escalating grader (uncertainty escalation + pedagogical-error-cost routing)

**Files:** `litnav/nodes/grade_kp.py`; Test `tests/test_grade_escalation.py`.

Spec §6.3 + §5 escalation gate: grade returns a confidence; **when the grade is low-confidence AND the learner is near the mastery threshold (a wrong call is pedagogically costly), escalate to the `frontier` model to re-grade** (or flag). 0–5 internally → normalized.

- [ ] **Step 1: failing test** (offline-deterministic via monkeypatched router): a cheap grade with `confidence < CONF_MIN` while mastery is in the threshold band [0.5, 0.85] triggers a SECOND `router.complete_json(tier="frontier", stage="grade_escalate")` call; outside the band (clearly mastered/clearly not) it does NOT escalate. Assert the frontier call count.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** in `grade_kp`, have the cheap grader also return a `confidence ∈ [0,1]` and a `score_0_5`. Compute `near_threshold = KP_MASTERY_THRESHOLD - 0.3 <= mastery <= KP_MASTERY_THRESHOLD + 0.05`. If `confidence < CONF_MIN (0.6)` AND `near_threshold` → re-grade once with `tier="frontier"` (the pedagogical-error-cost rule: spend frontier tokens only where a wrong correctness call near the threshold is costly), record the escalation + reason in the decision/history. Map `score_0_5` → correct/feedback. Keep the offline fallback path. Record both calls in `cost_ledger` (already metered via T1).
- [ ] **Step 4:** run + verify_m2/m3 green (offline: confidence from fallback is high → no escalation → unchanged behavior) + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow4): grade uncertainty escalation to frontier near the mastery threshold (escalation gate)`.

---

## Task 4: Bloom-leveled MCQ distractors + SAQUET flaw gate + IRT difficulty (weaker simulator)

**Files:** Create `litnav/assess/quizgen.py`; Modify `litnav/nodes/assess_next.py`, `litnav/storage/repo.py` (write distractors_json/irt_b); Test `tests/test_quizgen.py`.

- [ ] **Step 1: failing tests:**
  - `quizgen.make_distractors(question, answer_key, *, conn, session_id)` → overgenerate (cheap LLM) N candidate distractors, rank by plausibility, return top 3; offline fallback = candidate distractors.
  - `quizgen.flaw_gate(item)` (SAQUET-style) → rejects items with: a distractor equal to the answer, fewer than 2 distinct distractors, or an empty stem. Returns (ok: bool, reason).
  - `quizgen.estimate_difficulty(item, *, conn, session_id)` → asks a **weaker/cheaper** simulator (the `cheap` tier, with a "answer as a struggling student" prompt) to attempt it; maps wrong→harder; returns `irt_b ∈ [-3,3]`. Offline = a fixed mid value.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement `litnav/assess/quizgen.py` (router-metered, offline fallbacks). In `assess_next`, when generating an MCQ-type item, attach distractors (after the flaw gate; regenerate once if it fails, else fall back to short-answer), and store `distractors_json` + `irt_b` via `repo.create_quiz_item` (extend it to accept `distractors_json`/`irt_b`). Respect `bloom_ceiling` from T2.
- [ ] **Step 4:** run + verify_m2/m3 green (short-answer path unchanged offline) + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow4): MCQ distractors (overgenerate-rank) + SAQUET flaw gate + weaker-simulator IRT difficulty`.

---

## Task 5: FSRS spacing (review_queue) + delayed retention probe

**Files:** Create `litnav/assess/spacing.py`; Modify `litnav/nodes/advance.py` (or the mastery transition), `litnav/storage/schema.py` (retention log), `litnav/state.py`; Test `tests/test_spacing.py`.

- [ ] **Step 1: failing tests:**
  - `spacing.schedule_review(conn, session_id, concept_id, *, mastery, now)` — when a concept is mastered, compute an FSRS-lite next-due (interval ∝ 1/(1-recall_prob), recall_prob from mastery; first interval short) and `enqueue_review`. At `mastery ≥ 0.95` → fast-forward (longer interval / skip near-term re-practice).
  - `spacing.due_probes(conn, session_id, now)` — returns concepts whose `review_queue.due_at <= now`.
  - retention probe: `spacing.log_retention(conn, session_id, concept_id, *, predicted, actual)` writes a `retention_log` row (predicted mastery at scheduling vs actual at probe).
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** schema: `CREATE TABLE retention_log (session_id, concept_id, predicted REAL, actual REAL, probed_at TEXT)`. `litnav/assess/spacing.py` with FSRS-lite (deterministic math; pass `now` in — no `datetime.now` in core, per the no-clock rule; the node passes a timestamp). When `advance_kp`/concept-mastery fires, call `schedule_review`. A due probe re-quizzes and logs predicted-vs-actual (honest internal-validation signal; never a durable-learning claim).
- [ ] **Step 4:** run + verify_m2/m3 green + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow4): FSRS-lite review_queue spacing + delayed retention probe (predicted-vs-actual log)`.

---

## Task 6: teach strategy policy + metacognitive reteach (anti-over-help)

**Files:** `litnav/nodes/teach_kp.py`, `litnav/nodes/reteach_kp.py`; Test `tests/test_teach_strategy.py`.

- [ ] **Step 1: failing tests:** `teach_kp` picks a strategy from a cheap deterministic policy `strategy(goal_type, expertise, kp_mastery)` (e.g. low mastery → worked-example/direct; mid → analogy; survey-goal → concise overview). `reteach_kp` prepends a **metacognitive prompt** ("before the explanation, what part felt unclear?") and never reveals the answer key first (anti-over-help — assert the reteach prompt does not contain the answer_key verbatim).
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** add `litnav/assess/strategy.py::choose_strategy(goal_type, expertise, mastery) -> str` (pure deterministic policy — no LLM). `teach_kp` selects the strategy and passes it into the (router-metered) teaching prompt. `reteach_kp` adds the metacognitive lead-in + the anti-over-help constraint in the prompt.
- [ ] **Step 4:** run + verify_m2/m3 green + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow4): teach strategy policy (goal×expertise×KT) + metacognitive anti-over-help reteach`.

---

## Task 7: verify_teach_assess (offline unit) + verify_teach_assess_live (capability) + report

**Files:** Create `litnav/evaluation/verify_teach_assess.py`, `litnav/evaluation/verify_teach_assess_live.py`; Test `tests/test_verify_teach_assess.py`.

- [ ] **Offline unit gate** (`verify_teach_assess`): deterministic — goal heuristic, bloom-ceiling cap, flaw gate rejects a bad item, FSRS interval math, escalation-band logic (with monkeypatched grader), retention-log write. Assert + `pytest` entry.
- [ ] **LIVE gate** (`verify_teach_assess_live`, skips at provider=none): run a real short teach→assess→grade turn on a digested concept; assert `was_live`, grading metered (cost_ledger stage=grade), escalation fires when forced near-threshold + low-confidence, a distractor item passes the flaw gate, a review is scheduled. Print the cost table.
- [ ] **commit** `feat(ow4): verify_teach_assess offline unit gate + verify_teach_assess_live capability gate`.

## Controller live verification → three-part report (NOT a subagent task)
Run `verify_teach_assess_live` LIVE; produce the three-part report (live usage + cost table — show cheap grade vs escalated frontier grade — + evaluation: does escalation fire only where it should? distractor quality? optimize? actions). Update `docs/OPEN-WORLD-STATUS.md` OW-4 row. Final spec §6.3 re-check.

## Self-Review
- Every §6.3 line traced to a task (table above); escalation gate (OW-0 deferral) = T3; metered-router foundation = T1. ✓
- Live-first: T7 live gate + controller report; offline gates stay green per task (offline fallbacks preserve `verify_m2/m3`). ✓
- No new ENABLED model (escalation uses the existing `frontier`; weaker simulator uses `cheap`). ✓
- Reuses + extends main's inner loop; new modules under `litnav/assess/`; no rebuild. ✓
- Type consistency: `goal_type`/`bloom_ceiling` in NavState; `choose_strategy`, `make_distractors`/`flaw_gate`/`estimate_difficulty`, `schedule_review`/`due_probes`/`log_retention` names consistent across tasks. ✓
