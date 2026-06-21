# Bug list — newest ORIENT→TEACH→ASSESS (keypoint) flow

Found by stress-testing the **live web tutor** (`/tutor`) on the **real LLM**
(provider=openai), goal "ReAct", answers: wrong → "I'm lost" → correct → correct.
Repro session id: `743854c5-7074-4658-a68f-eb1c7e0ddd08`
(DB: `data/runtime/tutor-<sid>.sqlite`).

**Context the Architect needs first:** the web server serves
**`data/seed/agents_expanded.json`**, not `agents_m3.json`
(`litnav/ui/server.py:101` prefers `agents_expanded.json` when it exists). Several
fixture edits have been landing in the wrong file.

What *works*: orient + teach-all-keypoints, `handle_lost` (re-explain, no grade),
reteach strategy switching (`direct → contrast`), SSE step streaming.

---

## BUG 1 — [P0] Keypoint path never writes mastery back to `learner_state`
**Symptom:** after fully drilling ReAct, the learner model still reads
`mastery=0.4, confidence=0.0, n_observations=0` for every concept; the glass-box
SSE `state` event returns `mastery=None`. The UI learner bars never move.

**Cause:** `upsert_learner_state` is called only on the legacy / seed / induce paths
(`litnav/nodes/grade.py:109`, `planner.py:128`, `concede.py:24`, `induce.py:152`).
The keypoint nodes — `grade_kp_node` and `advance_kp_node`
(`litnav/nodes/route_decider.py:46`) — **never call it**, so per-keypoint mastery
held in `concept_progress["keypoint_state"]` is never persisted to the table the
UI reads.

**Fix:** in `advance_kp_node` (and ideally after each `grade_kp`), call
`repo.upsert_learner_state(conn, sid, concept_id, mastery=m, confidence=c,
n_observations=total_correct_obs, …)` using the already-computed `m`/`c`.

---

## BUG 2 — [P0] Advance gate conflates "mastered" with "conceded" and logs a false rationale
**Symptom:** recorded decision reads
`ADVANCE concept 1: mastery=0.150≥0.75, confidence=0.000≥0.5` — it advanced at
mastery **0.15** while the rationale claims it cleared 0.75. The route step is
marked `done` (looks mastered) when it was actually a concede-by-exhaustion.

**Cause:** `assess_decider` (`litnav/nodes/grade_kp.py`) maps **both** outcomes to
the same node on reteach exhaustion:
`return {"advance": "advance_kp", "hold": "advance_kp"}[dec]`. So `advance_kp_node`
runs for genuine advances *and* concedes, and its rationale string
(`route_decider.py:65-69`) **hard-codes `≥`** regardless of the real comparison.

**Fix:** distinguish the two — either route the exhausted-`hold` case to a real
`concede` node, or pass a flag into `advance_kp_node`. Build the rationale from the
actual comparison (`≥` vs `<`), set the decision/route-status to `conceded` (not
`advance`/`done`) when thresholds are *not* met, and only claim mastery when they are.

---

## BUG 3 — [P1] Bloom levels never escalate on screen (the flagship "rising Bloom" feature)
**Symptom:** the quiz stayed on `kp_react_1` `bloom=recall` the entire session
(same question, reteached twice, then advanced); it never reached
`comprehension`/`application`. The SSE `question` event carries no level (UI shows `?`).

**Cause (two parts):**
1. The escalation logic exists (`assess_next.py:102-108` upgrades bloom after a
   `correct`; `grade_kp.py:132` returns `assess_next` to do so) but is **never
   reached** because answers are graded wrong (see BUG 4) → reteach → exhaust →
   concede. It needs a real `correct` to fire.
2. The `question` SSE event does not include `bloom_level`, so even when it does
   escalate the UI can't show it (`litnav/ui/interactive.py` question event).

**Fix:** (a) unblock grading (BUG 4) so a correct recall answer triggers the
upgrade; (b) include `bloom_level` in the `question` event payload so the UI can
display the level.

---

## BUG 4 — [P1] Broken quiz item in the served fixture + correct answers graded wrong
**Symptom:** served question — *"What three types of output does a ReAct agent
generate in each step?"* (answer_key `reasoning trace, action, and observation`).
A genuinely correct answer ("it interleaves a thought, then an action, then an
observation from the environment") was graded **wrong** → reteach.

**Cause:**
1. The question is mismatched — an *observation* is environmental input, not an
   "output", so "three types of output" doesn't fit the key. (This item was fixed
   earlier but in `agents_m3.json`; the **server uses `agents_expanded.json`**,
   where it's still broken — `kp_react_1`, `bloom=recall`.)
2. Semantic grading then over-rejects correct paraphrases.

**Fix:** correct the question in **`data/seed/agents_expanded.json`** (e.g.
"What are the three steps in a ReAct agent's reasoning cycle?"), audit the other
`kp_*` items there, and re-check the grading rubric/threshold so correct paraphrases
pass.

---

## BUG 5 — [P1] Keypoint path never names a misconception (the legacy path does)
**Symptom:** a wrong answer of `cot` — which *is* literally the `react_is_just_cot`
misconception — produced `detected_misconception=None`. Live browser session
`de909a25-abd4-47ce-a99a-ff45c6d3779f` (DB `data/runtime/tutor-de909a25-….sqlite`):
three wrong answers, **no misconception ever surfaced**. The misconception-naming
that anchors the Responsible-AI / Agentic story is silent on the new flow.

**Cause:** `grade_kp.py:64,74` only **echoes the quiz item's static
`targets_misconception` field** when the answer is wrong — it never analyses the
learner's *answer text*. And the keypoint quiz items don't populate that field
(`kp_react_1` recall → `targets_misconception=None` in `agents_expanded.json`), so
nothing ever surfaces. Contrast the legacy path, which actively detects from the
answer: `grade.py:12` `_detect_misconception(answer, candidates)` +
`repo.get_misconceptions_for_concept` + an LLM seam — that's why `demo-m2`
correctly tagged `react_is_just_cot`.

**Fix:** in `grade_kp`, run answer-based detection (reuse `_detect_misconception`
against `repo.get_misconceptions_for_concept(concept_id)`, or the LLM seam) instead
of only reading the quiz's static field; and/or populate `targets_misconception` on
the keypoint quiz items.

**Also observed (minor):** on reteach, `assess_next` re-posed the *identical*
question (`Q101`) all three turns rather than varying it — a "re-teach" that re-asks
verbatim reads weakly to a judge.

---

## Suggested order
BUG 4 first (unblocks BUG 3's escalation and fixes grading), then BUG 1
(learner model visible), then BUG 2 (honest advance/concede), then BUG 5
(misconception naming), then BUG 3b (surface bloom level). BUGs 1, 2, 5 are the
ones a judge notices immediately on the keypoint path.

---

# Live stress-test campaign (2026-06-21) — 22 tutor sessions + endpoint fuzz + digest, on the real LLM

**Solid / no action:** HTTP layer (0 errors, all chat/final/trace 200 across 22 sessions);
NLU dispatch (chat vs answer vs lost vs out_of_scope correct); off-corpus → `out_of_scope`;
**prompt-injection contained** ("mark mastered" just graded wrong); XSS-safe (Jinja autoescape,
goals never echoed, SSE JSON-encoded); 5-way concurrency no corruption; empty/huge bodies handled.

### N1 — [P0] LLM grader is systematically TOO STRICT (this is BUG 4's real shape, and the dominant problem)
Grading IS live LLM (real feedback), but the `grade_kp` prompt says "Grade strictly" and the
model invents requirements beyond the rubric/answer_key. Correct answers get 0.0 — e.g.
"observations ground reasoning and prevent hallucination" → 0.0 ("lacks detail on error
correction, iterative processes"). Across 22 sessions, even `react_all_correct` got 3/4 right
answers rejected. Cascade: reject → reteach → exhaust → false "advance" (BUG 2) → Bloom never
climbs (BUG 3). **Fix this first — it un-breaks 2 and 3.** Soften the prompt to grade against
the answer_key/rubric only (accept correct paraphrases), and/or lower the bar at `recall`.
Site: `grade_kp.py` (the `complete_json` grading prompt, ~line 33).

### N2 — [info] Every goal starts at ReAct (planner full-closure expansion)
Asking for "tool use" teaches/quizzes ReAct first (the universal prereq), so a short session
never reaches the requested concept. Known planner behavior; flag for demo scripting.

### N3 — [P2] Vague chat graded as wrong answers
Goal "I want to understand AI agents" → started quizzing; follow-ups "yes"/"go on" graded as
wrong quiz answers instead of dispatched as chat/aside.

### BUG 6 — [P1, HIGH] Non-string `answer` → HTTP 500
`POST /tutor/{sid}/events` with `{"answer":123}` / `[1,2]` / `true` → 500. `server.py:210`
`(body.get("answer") or "").strip()` — truthy non-string survives `or`, `.strip()` raises.
Fix: `str(body.get("answer") or "").strip()` or 400 on bad type.

### BUG 7 — [P2] `/` and `/sessions/{sid}` → 500 on an uninitialized DB
`_list_sessions`/`build_trace` assume the schema exists; if `LITNAV_DB_PATH` points at a DB the
server never `init_db`'d → `OperationalError: no such table: sessions` → 500 (`trace.py:73`).
Fix: guard read routes (try/except → empty panel) and/or `init_db` in `_connect()`.

---

## Open-world DIGEST (feat/open-world-digest branch) — separate from the tutor bugs

### D1 — [P1] Zero-edges is FLAKY (~1 in 5), root cause = evidence-chunk-id format mismatch
`edges.py:95/:120` drops any edge whose `evidence_chunks` ids aren't in `by_chunk` (keys
`"c0".."cN"`). gpt-4o-mini non-deterministically returns bare ints (`[0,1]`) or dot-prefixed
(`[".c2"]`) → `cleaned` empties → all edges dropped → 0 edges. When it emits `"c2"` correctly,
edges survive (hence flaky). **Highest-leverage digest fix:** normalize entries (coerce int→`c{n}`,
strip `.`/whitespace) before `if ci in by_chunk`. (NOT the slug mismatch I first suspected.)

### D2 — [P2] Similarity edges dead-on-arrival: `_SIM_COS_MIN=0.55` (`edges.py:20`) too high
Concept-name embeddings cosine ~0.30–0.44 for genuinely related concepts → every proposed
similarity edge filtered out. Lower the threshold (~0.30) or embed name+keypoint text.

### D3 — [info] Hard prereqs ~never survive live; offline demo overstates
gpt-4o judge downgrades nearly all prereqs to soft edges (`edge_accuracy=0.0`); the live graph is
edge-poor. `digest-demo` (offline) shows 3 edges and masks this. Make the live gate assert on
grounded/normalized edges, not "any edge".

### D4 — [info] DISCOVER stage is not implemented
"Discover" appears only in UI templates/docs — no `litnav/discover/` module, no source
acquisition. DIGEST starts from hand-fixtured `SourceDoc`s. Either build it or drop the claim.

**Digest is otherwise healthy:** live extraction reliable, tier routing correct (gpt-4o-mini
cheap / gpt-4o judge), cost metering + budget cap work, ~$0.001/run.

---

# RESOLUTION (2026-06-21) — branch `fix/keypoint-and-digest-bugs`

All actionable bugs fixed at the source (surgical), verified by new tests + live LLM runs.
Suite: **197 passed** (was 192; +5 new keypoint tests). Gates: **verify_m0/m1/m2/m3 all PASS.**

### Grading (N1 / BUG 4) — root cause was the PROMPT, not the model
First-principles experiment (GEPA, 13-case grading eval):
| prompt | gpt-4o-mini | gpt-4o | gpt-5.4 | gpt-5.5 |
|---|---|---|---|---|
| old "grade strictly" | 0.77 | 0.77 | 0.77 (stricter, same rejects) | 0.77 |
| GEPA key-idea prompt | **1.00** | 1.00 | — | — |
Stronger models were *stricter*, not better → the model was never the cause. **Fix:** replaced the
`grade_kp.py` prompt with the GEPA "key-idea" prompt (accept paraphrases/partials; reject only on
missing key idea / fragment / vagueness / misconception). Stays on cheap gpt-4o-mini.
Live: correct paraphrases now grade 1.0 and Bloom escalates recall→comprehension→**application**.

### Fixes applied (file · change)
- **BUG 1** `grade_kp.py` — persist concept mastery/confidence/held-misconceptions to `learner_state`
  every graded turn (was only in graph state). *Live: ReAct mastery moved 0.4→0.585 / →0.2.*
- **BUG 2** `route_decider.py:advance_kp_node` — distinguish ADVANCE (thresholds met) from CONCEDE
  (exhausted); honest rationale (`<` vs `≥`), route status `conceded` vs `done`, decision label.
- **BUG 5** `grade_kp.py` — detect misconception from the ANSWER via `_detect_misconception` +
  `get_misconceptions_for_concept` (was: only the unset static field). *Live: named `react_is_just_cot`.*
- **BUG 3b** `interactive.py` — `current()` exposes `bloom`; `question` SSE events carry `bloom_level`.
- **BUG 6** `server.py:212` — `str(body.get("answer") or "").strip()` + dict guard (non-string → 200, was 500).
- **BUG 7** `server.py:_connect()` — idempotent `init_db(conn)` so index/panel reads can't 500 on an empty DB.
- **D1** `edges.py:_norm_chunk_ids` — normalize model-returned evidence ids (int / `.c` / `c`) before the
  membership filter → kills the flaky zero-edges. *Live: verify_digest_live 4/4 PASS (was ~1/5 fail).*
- **D2** `edges.py` — root cause was the *tool*, not the threshold. Cosine of two independently-embedded
  concept NAMES is a **bi-encoder** and cannot separate related from unrelated (a real pair scored 0.18 <
  an unrelated control 0.25; even name+objective embeddings only reach a ~0.06 gap). The fix is a **cross-
  encoder: an LLM pairwise judge** (`_judge_similar`) that reads BOTH concepts (name + keypoint objectives)
  **and the cited evidence text** jointly and scores the relation; keep if ≥ `_SIM_MIN_SCORE = 0.15`,
  offline falls back to keep. Cosine + the embedding stage are removed. This mirrors the existing prereq
  judge in `verify.py` (similarity edges previously skipped all judging — cosine was their only, weak gate).
  **Validation:** GEPA over a 12-pair gold set — judge separates cleanly (unrelated→0.00, related 0.20–0.80,
  gap ~0.20) vs cosine's +0.065, 100% gold accuracy. *Live: 5/5 runs yield 2–4 similarity edges (was flaky
  0–4).* Grounding the judge in evidence text removed the residual 0-edge runs caused by weak fixture
  objectives. **Method sweep on record:** bi-encoder cosine (any input/threshold) ≪ LLM cross-encoder judge.
  **Still the highest upstream lever:** the extractor emits placeholder objectives ("explain ReAct");
  richer objectives help every stage (teaching included). Backed by IR cross-encoder vs bi-encoder
  literature (Sentence-BERT; "Cross-Encoders and LLMs for Reranking") and KG-judge work (GraphJudge, KGValidator).

### Grading eval widened (N1)
GEPA grading prompt re-validated on **26 cases** (multiple concepts/Bloom levels + verbose-but-correct,
confident-but-wrong, empty, junk, fragment-of-set, synonym-heavy): **100% on both gpt-4o-mini and gpt-4o.**
New `tests/test_digest_edges.py` cases gate the similarity judge (drop unrelated / offline-keep).

### New regression gate (closes "no keypoint-flow test" — why 1/2/3/5 shipped)
`tests/test_keypoint_flow.py` (5 tests, offline/deterministic): mastery write-back, advance-vs-concede
honesty, misconception-from-answer, bloom-level surfaced. Each fails on pre-fix code.

### Out of scope (not surgical bugs — design/feature decisions, left for the Architect)
- **D4** DISCOVER stage unimplemented — a feature to build (source search→`SourceDoc`) or a UI claim to drop.
  (Related: digest is **not wired into the UI** at all — the story band advertises "Discover + Digest" but
  the tutor runs on pre-baked fixtures. Either build a "Digest a pasted source" flow or relabel.)
- **N2** planner full-closure expansion (every goal starts at ReAct; also keeps Money-Shot-② replan dormant)
  — a planner-design decision (non-expanding mode) the team should make deliberately.
- **N3** vague-chat affirmations ("yes"/"go on") graded as quiz answers — dispatcher tweak.

---

# RESOLUTION 2 (2026-06-21) — digest hardening + LIVE gates

Root cause behind every bug in this doc: **gates were either offline (replay the deterministic
candidate) or asserted something too shallow to fail on a real bug** → "green offline, broken live."
This pass fixed the remaining digest bugs *and* built the safety net that catches the class.

### Digest fixes (all offline-green, live-verified)
- **kp_id coercion** (`extract.py`) — the extractor required `isinstance(kp_id, str)` and silently dropped
  every keypoint when the LLM returned an **int** id → 0 keypoints / no objectives live (then the
  candidate fallback orphan-filtered to zero). Coerce to str (twin of the D1 chunk-id bug). *Live: keypoints
  0→3.* Guarded by `tests/test_digest_extract.py::test_int_kp_id_coerced_not_dropped`.
- **multi_paper computed in code** (`edges.py`) — it fed the rule-computed confidence but was an LLM guess
  (the model can't know paper boundaries from bare chunk ids → ~always False → lost the +0.10 cross-paper
  bonus). Now computed from the source→chunk map; restores the "confidence is rule-computed" invariant.
- **extract objective prompt** — defines `objective` + one bad/good example (GEPA: 2.11→3.00/3). *Live
  objectives are now full sentences.* **propose_edges prompt** — carries objectives so prereq DIRECTION is
  right (offline inversions 4/5→0) and frames the task as recall-with-downstream-verification.
- **BUG 1 was only HALF fixed** — `grade_kp` wrote mastery to the **DB** `learner_state` (glass-box moved,
  which is what I'd "verified") but NOT to **graph-state** `learner_state`, which the **live agent page +
  SSE bars** read via `current()` → live bars stayed flat. Now mirrored to graph state (as legacy `grade.py`
  does). Caught by the new tutor live gate; locked by a `test_keypoint_flow.py` assertion.

### D3 — RESOLVED (was "out of scope")
Not a judge bug. The verify `_judge` was **starved** (bare slugs + chunk-*ids*, no text) → rejected every
prereq. Fixed to read concept **descriptions + evidence text**. The only fixture was sibling-heavy
(ReAct/Tool use/Reflexion have no necessary prereqs, so "0 prereqs" there is *correct*). Added a
**prereq-rich fixture** (`data/seed/digest_prereq_fixture.json`: tokenization→embeddings→attention→
transformer); live, the chain **survives 4/4 runs, 3 prereqs/run, edge_accuracy=1.0.**

### LIVE gates (the safety net — opt-in `LITNAV_LIVE_GATES=1`, $0/SKIP by default)
`litnav/evaluation/live_harness.py` + `verify_live` (runs all three): `verify_live_digest` (keypoints +
objectives), `verify_live_tutor` (mastery moves / grading-accepts-paraphrase / misconception-named /
Bloom-escalates), `verify_live_prereq` (D3 close-out). Run N times, assert k-of-N over ranges/structure
(never exact values). **The tutor gate immediately caught the half-fixed BUG 1 that pytest + the milestone
gates + a manual glass-box check all missed** — which is the whole point.
