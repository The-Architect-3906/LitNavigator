# Design — Spaced Retrieval, Measured

**Date:** 2026-06-22 · **Status:** approved (brainstorming) → ready for writing-plans
**Branch:** `exp/research-improvement-loop`

## 1. Goal & success criteria
Deliver the dormant spaced-retrieval / testing-effect lever (the highest-leverage learning-science
add from the foundations audit, reusing infra that already exists), **and** give the eval a
delayed-retention metric so the feature's value is measurable.

**Success:** with a forgetting learner, delayed-retention `% retained` is **higher with the probe ON
than OFF** (`retention_gain > 0`) on the offline eval, the offline test suite stays green, and the
probe never disrupts the current lesson (no reteach, never blocks teaching).

## 2. Background (verified against current code, 2026-06-22)
- `litnav/assess/spacing.py` is complete: `interval_days`, `schedule_review` (producer),
  `due_probes` + `log_retention` (consumers) all exist.
- The producer is wired only on the **legacy** path (`litnav/nodes/advance.py:39`); the **primary
  keypoint path (`advance_kp`) never schedules a review**, and **no node calls `due_probes` /
  `log_retention`** — the consumer half is dead.
- `interval_days()` returns **days** (≥1), so `review_queue` is a **cross-session (calendar)**
  mechanism — nothing it schedules can come due within a single (minutes-long) session.

**Decisions (from brainstorming):**
- **Timing = in-session, turn-based** (a re-quiz of an earlier concept after K intervening concepts).
  The calendar `review_queue` is left untouched for the future cross-session story.
- **Probe effect = low-stakes:** always log predicted-vs-actual; correct → gentle reinforce; wrong →
  nudge mastery down + flag for later review; **never** trigger an immediate reteach.
- **Trigger = graph-state turn counter + a new `review_probe` node** (no schema change; calendar
  `review_queue` untouched). Rejected: repurposing `review_queue.due_at` as a turn counter (mixes
  calendar/turn semantics); folding into `select_next` (tangles the dispatcher).

## 3. Scope
**In:** in-session retrieval probe node + pure helpers; `NavState` step/last-seen tracking; the
delayed-retention eval metric + A/B (`retention_gain`) in the scorecard; tests.
**Out (YAGNI):** cross-session calendar delivery (review_queue stays as-is); any UI work; fitting FSRS
stability/lapse state; changing the legacy `advance.py` producer.

## 4. Components (each one job, testable in isolation)

### 4.1 `litnav/assess/retrieval.py` (new — pure, no I/O)
- `is_due(last_seen_step: int | None, current_step: int, k: int = 2) -> bool` — true if a concept was
  last seen ≥ `k` steps ago (and has been seen at least once).
- `predicted_recall(mastery: float) -> float` — the probe's predicted recall = current mastery
  (clamped 0–1); the value logged as `predicted`.
- `reinforce(mastery: float, correct: bool) -> float` — **low-stakes** update: correct → small bump
  toward 1.0 (`mastery + (1-mastery)*0.15`); wrong → small nudge down (`max(0, mastery-0.10)`).
  Distinct from `kp_bump` (gentler; retrieval is reinforcement, not first-learning).

### 4.2 `litnav/nodes/review_probe.py` (new — the graph node)
`review_probe_node(state, conn) -> dict`:
1. From `state["concept_last_seen"]` + `state["step"]`, pick the **most-overdue** mastered concept
   with `is_due(...)` true and a stored quiz available; if none → return `{}` (pass-through).
2. Pose that concept's **existing** quiz (reuse `repo.get_any_quiz_for_kp` / a cached item — do NOT
   generate new content); record it as a retrieval turn in `history`.
3. Grade the learner's answer with the **existing key-idea grader** (`router.complete_json`, cheap
   tier, deterministic offline fallback).
4. Apply low-stakes rule: `reinforce(mastery, correct)` → write back to `learner_state` (DB +
   graph-state, like `grade_kp`); if wrong, set a `needs_review` flag on that concept (no reteach).
5. `spacing.log_retention(conn, session_id, concept_id, predicted=predicted_recall(mastery_before),
   actual=1.0 if correct else 0.0, probed_at=<deterministic now from state>)`.
6. Update `concept_last_seen[concept_id] = step`; return updated state.
**Rationale string** is learner-friendly ("Quick recap of *X* before we move on").

### 4.3 `litnav/graph/builder.py` (wiring)
- Add `review_probe` node on the path **into a new concept**: `select_next → review_probe → retrieve`
  (or `init_kp`). A conditional edge routes `select_next → review_probe` only when a concept is due,
  else straight to teaching. `review_probe` always continues to teaching after (single probe per
  transition — no probe loops).
- `advance_kp` / `select_next` bump `state["step"]` and set `concept_last_seen` for the concept just
  finished (so the keypoint path now records "seen", the gap the audit found).

### 4.4 `NavState` (`litnav/state.py`)
- Add `step: int` (turn counter) and `concept_last_seen: dict[int, int]`. Optional `needs_review:
  list[int]`. Backward-compatible defaults (absent → start at 0 / empty).

## 5. Data flow
`advance_kp` (mark finished concept seen @ step) → `select_next` (++step; is anything due?) →
**`review_probe`** (if due: pose stored quiz → grade → `reinforce` + flag → `log_retention`) →
`retrieve`/teach next concept. Retention rows accumulate in `retention_log`.

## 6. The eval metric (the keep/revert gate)
Extend `litnav/eval/mastery_probe.py`:
- **Delayed-retention run:** teach all fixture concepts, then **re-quiz each without re-teaching**,
  scoring `retention = mean(correct)`. Use a **forgetting learner** (a profile whose recall decays
  with intervening concepts) so there is headroom.
- **A/B in one run:** run the delayed-retention probe with `review_probe` **ON vs OFF**;
  `retention_gain = retention_on − retention_off`.
- **Scorecard:** add `learning_gain.retention` and a top-level `retention_gain`. The loop keeps the
  feature iff `retention_gain > 0` and the offline suite stays green.

## 7. Error handling / safety
- No due concept, or no stored quiz for it → `review_probe` returns `{}` (pass-through); teaching is
  never blocked.
- Grader failure → skip the log, continue.
- Fully offline-deterministic (scripted learner + fallback grader; `now` passed in, never read from
  the clock) → CI-safe, and the eval loop can gate it.
- Single probe per concept-transition (no probe→probe loops); `review_probe` always exits to teaching.

## 8. Testing
- **Unit (pure):** `is_due` (boundary at k), `reinforce` (correct bumps, wrong nudges, clamped),
  `predicted_recall`.
- **Node:** a due, mastered concept gets probed exactly once → `retention_log` row written, mastery
  reinforced/nudged, **no reteach node fired**, `concept_last_seen` updated; nothing-due → pass-through.
- **Eval:** `retention_gain > 0` for the forgetting learner (probe ON vs OFF); offline suite green.

## 9. Open risks
- The forgetting-learner model is synthetic — `retention_gain` proves the *mechanism* wires through
  and helps a learner that forgets; it is not a human-subjects claim. Documented as such.
- K=2 default is a guess; surfaced as a constant, easy to tune once the metric exists.
