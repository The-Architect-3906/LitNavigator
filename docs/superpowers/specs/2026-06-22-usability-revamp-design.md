# Design — LitNavigator Usability Revamp (backend blockers + UI Direction B)

**Date:** 2026-06-22 · **Status:** approved (brainstorming) → ready for writing-plans
**Branch:** fresh slice off latest `feat/open-world-digest`.

## 1. Goal & success criteria
Lift the **live** tutor experience from a measured **2.5/5** toward genuinely usable. Two parallel
tracks: **(A) fix the backend blockers** the live E2E test exposed (they cap usability regardless of
looks), and **(B) the Direction-B "Living Glass-Box Instrument" UI redesign**.

**Success:** a re-run of the 10-scenario live user-test rates **≥4/5 average**, with the 3 universal
killers gone (correctness feedback shown; cited evidence populated; mastery reachable + grading
sane); the offline suite stays green; and the tutor *looks* like a trustworthy instrument, not a plain
form.

**Evidence base (do not re-derive — read these):** `docs/eval/e2e-qa-report.md` (19 ranked bugs
B1–B19 + per-scenario ratings), `docs/eval/ui-improvement-spec.md` (45 sweep findings + 32 ideas +
file:line locations), `docs/eval/ui-redesign-directions.md` (Direction B full visual system + layout +
interactions; A/C kept as future inspiration).

## 2. Track A — backend blockers (TDD, the bigger usability lever)
Each is verified live + root-caused in the QA report. Fix + add a regression test; offline-deterministic
where possible, else a small live gate.

- **A1 (B1/B2) — grader + mastery reachability.** Live confidence caps below the 0.5 advance gate so
  concepts concede instead of mastering; grading is also non-monotonic (vague→1.0, expert→0.0).
  Fix the advance-gate/confidence math so a correct learner *can* reach mastery, and tighten the
  key-idea grade prompt so correctness beats verbosity. Test: a scripted always-correct learner
  reaches `done` (not `concede`) on a multi-keypoint concept; a golden grading set stays ≥ baseline.
- **A2 (B4) — cited evidence dark on the open-world path.** `evidence:[]`, `cited:[]`, retrieve logs
  "0 chunks". Make digested keypoints carry their evidence chunk through to `current().cited` /
  `trace.evidence`. Test: an open-world session yields non-empty `cited` on teach turns.
- **A3 (B5) — `trace.total_token_cost` stuck at 0.** `trace.py:224-225` sums
  `tutor_turns/decisions token_cost` (0 live); real spend lives in `cost_ledger`. Sum `cost_ledger`
  (the fix already applied in `ui/cost.py`). Test: live cost > 0 surfaces in the trace.
- **A4 (B6) — misconception detection never fires.** Baited misconceptions all return
  `detected_misconception=null`. Wire `_detect_misconception` against the concept's bank on the live
  path; reteach names the specific false claim. Test: a baited wrong answer sets the misconception.
- **A5 (B7) — "I don't know" punished.** It dispatches `action=answer` → 0.0 → tanks mastery, while
  "I'm lost" routes to `handle_lost`. Route "I don't know"/equivalent to the no-penalty lost path.
  Test: "I don't know" does not drop mastery.
- **A6 (B8/B9) — relevance gates.** Goal→corpus too loose ("build Raft" → a Coq proof paper; ReAct →
  reactance) and answers aren't relevance-checked (off-topic carbonara passed). Add the DISCOVER
  topic-match gate (also Track B's blocker) + a minimal answer-relevance guard. Gate: the adversarial
  DISCOVER battery on-topic rate rises from 77%.
- *Lower-priority cleanups (B10–B19): stale `state.decision`, trace-lags-one-turn, difficulty not
  de-escalating after "I'm lost", empty completion bubble, etc. — batch as a follow-up task.*

## 3. Track B — Direction B UI redesign
Full detail in `ui-redesign-directions.md`. Scope here:

**Design system (retire `#5b49c4`, the storyband gradient, `system-ui`):** Geist Sans body + Geist/
Berkeley **Mono for all numerals**; dark-first **4 surface levels by lightness** + hairline borders;
**one accent** amber-gold `#E0A33C`; fixed semantic tokens (green=mastered, amber=conceded/boundary,
gray=pending); motion tied to real agent events + `prefers-reduced-motion`.

**Layout:** glass-box-primary; chat is a column within the instrument.

**Phase 1 (this spec):**
- the dark design system + type + semantic tokens (CSS variables in `agent.html`)
- **feedback bubble** on grade (B3 — also Track A data) — correct/wrong + the key idea
- **inline citation chips** in lesson prose → evidence cards (graft from A); chat↔glass cross-highlight
- **named mastery tiers** (Seen→Familiar→Solid→Mastered) + plain-language **"why this next"** chip (graft from C)
- **live named-step working indicator** (replace the static dot) + staged 4-step build tracker
- **empty states** on every glass-box panel + symmetric first paint (`current()` adds cost/recommend; learner[] all route concepts)
- **inline error + Retry** (kill the 3 blind `location.href` reloads)
- **a11y + quick wins:** viewport meta on home, input labels, `<h1>`, conditional cost label, reduced-motion, `aria-live`, `role=progressbar`, contrast, focus rings

**Phase 2 (deferred, separate plan):** decision-trail timeline, confidence-as-uncertainty-band, ⌘K
palette, interactive concept map, persistent artifact tab.

## 4. Verification
- **Track A:** unit/golden tests per fix + offline suite green; then re-run the **adversarial DISCOVER
  battery** + a **subset live user-test** to confirm the killers are gone.
- **Track B:** visual check in the running UI + the live user-test re-rating (target ≥4/5). No pixel
  TDD; verify by driving real sessions (the proven HTTP driver) + inspecting the rendered page.
- **The eval harness + the E2E user-test workflow are the report card** for both tracks.

## 5. Scope guard (YAGNI)
P2 bigger bets deferred to their own plan. B10–B19 minor bugs batched as one cleanup task. A/C visual
directions are future inspiration, not this build. No new pipeline stages.

## 6. Open risks
- The grader/mastery fix (A1) touches core advance logic — must not regress the 394-green suite or the
  keypoint-flow gates; needs careful TDD.
- Track B is a large visual change; phasing (P1 now, P2 later) keeps each shippable. Both tracks land
  on one branch but as separable commits so either can be reverted.
