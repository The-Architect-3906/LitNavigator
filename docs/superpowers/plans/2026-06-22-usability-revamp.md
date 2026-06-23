# Usability Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Track A is debugging** — use superpowers:systematic-debugging per task (reproduce → diagnose → fix → verify); the "likely fix" is a lead, confirm it before coding.

**Goal:** Lift the live tutor from 2.5/5 toward ≥4/5 by fixing the backend blockers (Track A) and shipping the Direction-B "Living Glass-Box Instrument" UI redesign Phase 1 (Track B).

**Architecture:** Two independent tracks on one branch (`feat/usability-revamp`), separable commits. Track A = surgical fixes to grader/mastery/retrieve/trace/dispatch with pytest regression tests. Track B = a dark design-system + presentation rewrite in `litnav/ui/templates/agent.html` + `interactive.py`/`trace.py` data wiring, verified by driving real sessions.

**Tech Stack:** Python 3.14, LangGraph, FastAPI/uvicorn, SQLite, Jinja templates + vanilla JS/CSS, pytest. Live LLM via litellm **1.83.7** (Py-3.14 ceiling; `>=1.89` won't install here).

## Global Constraints
- Always use the venv: `.venv/bin/python`. Branch: `feat/usability-revamp`.
- **Offline suite (litnav tests) must stay green** after every Track A task. Mastery/confidence stay **rule-computed**, never LLM-emitted.
- Verification report card for both tracks: the eval harness (`litnav/eval`), the adversarial DISCOVER battery, and a re-run of the 10-scenario live user-test (via the proven HTTP driver) targeting **≥4/5**.
- Evidence base (read, do not re-derive): `docs/eval/e2e-qa-report.md` (B1–B19), `docs/eval/ui-redesign-directions.md`, `docs/eval/ui-improvement-spec.md` (file:line locations).
- **These could be two plans** (Track A backend / Track B UI). Kept together because they ship one usability lift; execute A first (caps usability) or interleave.

---

# TRACK A — Backend blockers (systematic-debugging + TDD)

## Task A1: Mastery reachable on the live/digested path (B1)
**Files:** `litnav/nodes/route_decider.py`, `litnav/state.py` (`kp_confidence`/thresholds), `litnav/digest/pipeline.py` (`_propose_quiz_seeds` quiz count) · Test: `tests/test_mastery_reachable.py`
**Symptom:** live confidence caps ~0.3 < `KP_CONF_THRESHOLD=0.50` (needs `correct_obs≥2`); digested concepts often have too few quizzes for a second correct observation → every concept `concede`s.

- [ ] **Step 1 — reproduction test (failing):** seed a digested-style concept with ONE keypoint + ONE quiz; drive grade_kp with correct answers + advance_kp; assert it reaches `done`, not `conceded`.
```python
# tests/test_mastery_reachable.py
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes.grade_kp import grade_kp_node, assess_decider
from litnav.nodes.route_decider import advance_kp_node
# (build a 1-keypoint, 1-quiz concept; answer correctly; assert advance_kp marks "done")
```
- [ ] **Step 2 — run, confirm FAIL** (`concede` not `done`): `.venv/bin/python -m pytest tests/test_mastery_reachable.py -v`
- [ ] **Step 3 — diagnose:** confirm whether the cap is (a) too few quizzes (`correct_obs` can't reach 2) or (b) the confidence curve. Inspect `kp_confidence` + `_propose_quiz_seeds` count.
- [ ] **Step 4 — fix (likely):** make `correct_obs` accrue across the Bloom climb of the SAME keypoint (a correct recall→comprehension→application counts as ≥2 observations), OR have digest seed ≥2 quizzes per keypoint, OR set `KP_CONF_THRESHOLD` to clear at the achievable obs count. Pick the one diagnosis supports; keep mastery rule-computed.
- [ ] **Step 5 — run test PASS + full offline suite green** (`.venv/bin/python -m pytest -q`).
- [ ] **Step 6 — commit** `fix(grade): mastery reachable on digested concepts (B1)`.

## Task A2: Cited evidence populated on the open-world path (B4)
**Files:** `litnav/nodes/teach_kp.py`, `litnav/nodes/retrieve.py`, `litnav/ui/interactive.py` (`current().cited`) · Test: `tests/test_open_world_cited.py`
**Symptom:** `evidence:[]`, `cited:[]`, retrieve logs "0 chunks" though digest wrote `paper_chunks` and keypoints carry `evidence_chunk_id`.

- [ ] **Step 1 — failing test:** seed a digested concept whose keypoint has a real `evidence_chunk_id`; call `teach_kp_node`; assert the returned state sets `current_cited_chunks=[that id]`.
- [ ] **Step 2 — run, confirm FAIL** (empty).
- [ ] **Step 3 — diagnose + fix:** `teach_kp` reads the evidence into the prompt but must also return `current_cited_chunks=[kp_meta["evidence_chunk_id"]]` (same gap fixed earlier on the fix branch); confirm `current().cited` reads it. If retrieve still reports 0 chunks, trace `retrieve_node`'s chunk lookup for digested concepts.
- [ ] **Step 4 — PASS + suite green. Step 5 — commit** `fix(teach): surface keypoint evidence as cited on open-world path (B4)`.

## Task A3: Real cost in the trace (B5)
**Files:** `litnav/ui/trace.py:~224-225` · Test: `tests/test_trace_cost.py`
**Root cause (confirmed by testers):** sums `tutor_turns/decisions.token_cost` (0 live); real spend is in `cost_ledger`.

- [ ] **Step 1 — failing test:** seed a `cost_ledger` row (tokens>0) for a session; assert `build_trace(...)['total_token_cost'] > 0`.
- [ ] **Step 2 — FAIL. Step 3 — fix:** sum `cost_ledger` (reuse `ui/cost.py:session_cost`) for `total_token_cost`, fall back to the old sum. **Step 4 — PASS + suite. Step 5 — commit** `fix(trace): total_token_cost from cost_ledger (B5)`.

## Task A4: Misconception detection fires live (B6)
**Files:** `litnav/nodes/grade_kp.py` (`_detect_misconception` wiring), `litnav/digest/pipeline.py` (does digest seed a misconception bank?) · Test: `tests/test_misconception_live.py`
**Symptom:** baited wrong answers all return `detected_misconception=null`.

- [ ] **Step 1 — failing test:** seed a concept WITH a misconception in the bank + a quiz; grade a wrong answer voicing it; assert `detected_misconception` is set.
- [ ] **Step 2 — FAIL. Step 3 — diagnose:** is the bank empty on the digested path (digest never seeds misconceptions), or is `_detect_misconception` not called? **Fix accordingly** — wire detection on the keypoint grade path and/or have digest emit ≥1 misconception per concept.
- [ ] **Step 4 — PASS + suite. Step 5 — commit** `fix(grade): misconception detection on the live path (B6)`.

## Task A5: "I don't know" is no-penalty, not a wrong answer (B7)
**Files:** `litnav/conversation.py` (`_LOST_CUES` / classify) · Test: `tests/test_idk_not_penalized.py`
**Root cause:** "I don't know" isn't in `_LOST_CUES`, so it classifies as `answer` → graded 0.0.

- [ ] **Step 1 — failing test:** assert the dispatcher classifies "I don't know" / "I dont know" / "no idea" / "idk" as `lost` (or a no-grade action), like "I'm lost".
- [ ] **Step 2 — FAIL. Step 3 — fix:** add those cues to `_LOST_CUES` (or a dedicated no-penalty branch that routes to `handle_lost`). **Step 4 — PASS + suite. Step 5 — commit** `fix(dispatch): treat "I don't know" as lost, not a failed answer (B7)`.

## Task A6: DISCOVER topic-match gate + answer-relevance guard (B8/B9 + the ReAct bug)
**Files:** `litnav/discover/relevance.py` or `find_sources.py` (gate), `litnav/discover/intent.py`/`query.py` (disambiguation), grade path (answer guard) · Test: extend `litnav/evaluation/verify_discover_adversarial.py` as the gate.
- [ ] **Step 1 — baseline:** run the adversarial battery live (currently **77%**, fails ReAct/attention). Record.
- [ ] **Step 2 — fix:** add a topic-match check — judge the chosen source's domain against the goal; if mismatched, disambiguate the query (add domain context for short terms) or decline honestly ("I only have <domain> sources"). Add a minimal answer-relevance guard so an off-topic answer can't pass grading.
- [ ] **Step 3 — verify:** battery on-topic rate rises (target ≥90%); offline suite green. **Step 4 — commit** `fix(discover): topic-match relevance gate + answer-relevance guard (B8/B9)`.

## Task A7: Minor trace/decision cleanups (B10–B19, batched)
**Files:** `litnav/ui/trace.py`, `litnav/nodes/*` · Test: targeted asserts where cheap.
- [ ] Fix stale top-level `state.decision` (B11); the one-turn trace lag (B12); difficulty de-escalation after "I'm lost" (B14); `handle_lost` writes a decisions/timeline entry (B15); empty completion bubble → a summary/congrats message (B16); `session.status`→done on completion (B18). One commit per 1–2 related fixes; suite green each time. **Commit** `fix(trace/flow): glass-box consistency cleanups (B10-B19)`.

---

# TRACK B — Direction-B UI redesign, Phase 1 (verify by driving real sessions)

> Verification pattern for every Track B task: restart the server, drive a session with `tmp/drive_session.py` (or open `/tutor` and curl the page), confirm the change renders and nothing regresses. No pixel-TDD.

## Task B1: Dark 4-surface design system + type + semantic tokens
**Files:** `litnav/ui/templates/agent.html` (`<style>` `:root`), `agent_home.html`
- [ ] Replace `#5b49c4`, the storyband gradient, and `system-ui` with CSS variables: 4 dark surfaces by lightness (`--s0..--s3`), hairline `--border`, one accent `--accent:#E0A33C`, semantic `--ok`(green)/`--warn`(amber)/`--idle`(gray); Geist Sans stack + a mono stack (`--mono`) applied to all numerals (mastery/confidence/cost/Bloom/counts); spacing on a 4px grid; wrap motion in `@media (prefers-reduced-motion: no-preference)`.
- [ ] Verify: `/tutor` renders dark, no purple/gradient, numerals are mono. Commit `feat(ui): dark 4-surface design system + type + semantic tokens (retire purple/gradient/system-ui)`.

## Task B2: Feedback bubble on grade (B3)
**Files:** `litnav/ui/interactive.py` (`stream_answer`/`_step_event`), `agent.html` (`handleEvent`)
- [ ] Emit a `{type:'feedback', correct:bool, text:'<key idea>'}` event from the grade step (data already computed: `last_feedback`, `last_detected_misconception`); render a distinct green/amber bubble. Verify by driving a session: a graded answer shows correct/wrong + why. Commit `feat(ui): feedback bubble on grade (B3)`.

## Task B3: Inline citation chips → evidence cards + cross-highlight
**Files:** `agent.html` (`handleEvent` 'teach' uses `e.cited`; `md()`), `#evidence` cards
- [ ] Render `[1][2]` chips in teach prose keyed to the teach event's `cited[]` (now populated by A2); clicking a chip activates the Cited-evidence tab + highlights the matching card; cards show paper title + quoted span + "used for: <keypoint>". Verify: chips appear and link. Commit `feat(ui): inline citation chips + evidence cards + cross-highlight`.

## Task B4: Named mastery tiers + plain-language "why this next"
**Files:** `interactive.py` (`current()` learner presenter), `flow_meta.py`, `agent.html` (`#learner`, `#why`)
- [ ] Map mastery→tier (Seen/Familiar/Solid/Mastered) shown as a segmented meter with the % as a quiet subscript; map decision tokens (advance/reteach/diagnose/concede/bloom-up) to learner sentences in a "why this next" chip; raw token behind the existing toggle; fix the dangling em-dash. Verify by driving a session. Commit `feat(ui): named mastery tiers + plain-language why-this-next`.

## Task B5: Live named-step working indicator + staged build tracker
**Files:** `agent.html` (`#working`, `setFlow`, `__BUILDING__`), `interactive.py` `_STEP_LABELS` + build sub-stage events
- [ ] Replace the static "● agent working…" with the live step name; replace the cold-start spinner with a 4-row tracker (Discover→Digest→Plan→Teach) flipping to a check + count as each `build` event lands, plus an elapsed timer; pulse the active step. Verify on a cold start. Commit `feat(ui): live named-step indicator + staged build tracker`.

## Task B6: Empty states + symmetric first paint
**Files:** `interactive.py` (`current()` 274-281 learner filter, 331-348 `AgentSession.current()`), `agent.html` panels
- [ ] `current()` includes `cost` + `recommend` (match SSE first-paint); `learner[]` includes all route concepts with a "not yet assessed" state (drop the `n_observations>0` filter); add explicit empty copy to evidence/learner/cost panels (e.g. "Citations appear as I teach each keypoint"). Verify: open glass box before any answer → panels read, not blank. Commit `feat(ui): glass-box empty states + symmetric first paint`.

## Task B7: Quiz "Knowledge Check · Bloom" card + recap framing
**Files:** `agent.html` (`.qa`, 'question' branch renders `e.bloom_level`, answer input), `interactive.py` `_STEP_LABELS['review_probe']`
- [ ] Quiz bubble gets a header chip "QUESTION · {bloom}" + a distinct accent border; input captions "Your answer"; the spaced-retrieval `review_probe` gets a "🔁 Recap — revisiting X" badge. Verify by driving to a quiz + (if present) a recap. Commit `feat(ui): knowledge-check + recap framing`.

## Task B8: Inline error + Retry (kill blind reloads)
**Files:** `agent.html` (`streamEvents` catch ~545, 'error' ~504, third reload ~489)
- [ ] Replace the 3 `location.href` reloads with an inline dismissible error bubble showing `e.message` + a Retry that re-runs the last `streamEvents` and re-enables input. Verify by simulating an error (stop the server mid-stream). Commit `feat(ui): inline error + retry (no blind reload)`.

## Task B9: A11y + quick-wins batch
**Files:** `agent_home.html`, `agent.html`
- [ ] Add viewport meta + an `<h1>` to `agent_home.html`; `<label>`/`aria-label` on both inputs; conditional cost label ("Offline — $0" when tokens==0, else real spend); `aria-live="polite"` on `#thread`/`#working`; `role="progressbar"`+`aria-valuenow` on mastery bars; `:focus-visible` rings; fix muted-text contrast to AA; move the goal form above the hero. Verify with a quick keyboard/contrast pass. Commit `feat(ui): a11y + quick wins batch`.

---

## Final verification (both tracks)
- [ ] Offline suite green; adversarial DISCOVER battery ≥90%.
- [ ] Restart server; **re-run the 10-scenario live user-test** (the same workflow/driver) → record the new usability rating. **Target ≥4/5**; if not, the gap report is the next backlog.

## Self-Review
- **Spec coverage:** Track A A1–A7 cover B1–B19; Track B B1–B9 cover the Direction-B P1 scope + the UI-spec blockers/quick-wins. P2 (timeline/uncertainty-band/⌘K/interactive-map/artifact-tab) explicitly deferred. ✓
- **Placeholders:** Track A fixes are diagnosis-led (systematic-debugging) with concrete reproduction tests + confirmed root causes where known (A3/A5) and leads where not (A1/A2/A4/A6) — flagged as such, not hidden TODOs. Track B steps name exact files/elements.
- **Consistency:** A2 (cited populated) feeds B3 (citation chips); B6 first-paint matches the SSE keys; B2 feedback event named consistently. Verified by the live user-test, not pixel tests, per spec §4.
