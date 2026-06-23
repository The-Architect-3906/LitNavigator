Ratings: S1=3, S2=3, S3=2, S4=3, S5=2, S6=3, S7=3, S8=4, S9=3, S10=2. Average = 2.8.

Here is the synthesized QA report.

---

# LitNavigator — Live Tutor QA Synthesis

**10 scenarios, 10 testers, ~99 driven turns.** Scenario index: S1 ML/diffusion (EN, mastery) · S2 CRISPR (ZH, survey) · S3 Raft (EN, functional) · S4 QEC (EN, survey) · S5 Black-Scholes (ES, mastery) · S6 mRNA vaccines (EN, functional) · S7 Transformer attention (ZH, mastery) · S8 Behavioral econ (EN, survey) · S9 RLHF (EN, functional) · S10 GNNs (FR, survey).

## 1. Overall Usability

**Average rating: 2.8 / 5** (S1=3, S2=3, S3=2, S4=3, S5=2, S6=3, S7=3, S8=4, S9=3, S10=2).

**Holistic read.** The tutor has an excellent skeleton wrapped around an unreliable core. Every tester praised the same three pillars — the cold-start build choreography, the adaptive reteach strategy ladder, and the glass-box decision rationales — and every tester hit the same wall: the learner can never tell if they were right, the grader is erratic-to-broken, and re-asked questions feel like a stuck loop. The score clusters at 3 because the experience is *legible and pedagogically thoughtful but not trustworthy*. The two 2s (S3, S5, S10) are where grading actively inverted: correct answers drove mastery to 0.0 and the session became uncompletable. The lone 4 (S8) is the existence proof — when grading happened to behave, the full ORIENT→TEACH→ASSESS→ADVANCE loop completed end-to-end and the product felt genuinely good.

**The 3 things that hurt most (cross-scenario):**

1. **No correctness feedback to the learner, ever.** No `feedback` event is emitted in any of the 10 scenarios. After answering, the learner jumps straight to the next question or a reteach with no "correct/incorrect + why." Pass and fail are indistinguishable from the learner's seat. Called the single biggest gap in S1, S3, S6, S7, S9, S10. `grade_kp.py` computes a grounded feedback string; the SSE layer never surfaces it.
2. **Grading is unreliable and sometimes inverted.** It is over-lenient in one scenario (S1: a contentless hedge scored 1.0) and over-strict to outright broken in others (S3, S5, S10: textbook-correct answers scored 0.0, mastery monotone-decreasing, advance threshold structurally unreachable, session uncompletable). It is binary (0.0/1.0, no partial credit) everywhere, and language-biased (S10: a correct French answer scored 0.0 where its English twin scored 1.0). This is the exact over-strict-grading regression CLAUDE.md warns about, firing on the LIVE path.
3. **Verbatim question repetition reads as a broken loop.** When Bloom rises within a concept or a learner is stuck, the identical question text is re-posed — up to 4 times in a row (S1, S4, S7) — with only the `bloom_level` label changing. Hit in S1, S2, S4, S6, S7, S9, S10.

## 2. Consolidated Bug List (deduped, ranked by severity then frequency)

### BLOCKER
- **B1. Grader marks correct answers wrong; mastery is monotone non-increasing; session uncompletable.** Correct, on-topic, key-idea-bearing answers graded `correct=False`, driving every concept to 0.0 and "conceded"; advance gate (mastery≥0.75 ∧ confidence≥0.5) never reachable. **Scenarios: S3 (4 concepts to 0.0), S5 (even a 1.0-scored turn left mastery 0.325, stayed "reteach"), S10 (correct answers scored against the wrong concept).** Live path, real token spend.
- **B2. No `feedback` event is ever streamed.** Learner cannot tell pass from fail. **Scenarios: S1, S3, S6, S7, S9, S10** (explicitly flagged blocker in S3/S10; major in S1/S6/S7/S9).
- **B3. Answer/question/score misalignment — answers graded against the wrong concept's keypoint.** Correct on-screen answers scored against a stale/other concept's reteach → registered as failures and concede. **Scenario: S10 (T6/T7/T8).**

### MAJOR
- **B4. Verbatim question repetition on Bloom rise and on stuck loops** (identical text, only label changes; up to 4× in a row). **Scenarios: S1, S2, S4, S6, S7, S9** (+ noted in S8, S10).
- **B5. Misconception detection never fires on the keypoint path.** `held_misconceptions` stays `[]` and `detected_misconception` stays null even on blatant, taggable misconceptions. **Scenarios: S1, S2, S4, S7, S8, S9, S10** (near-universal). S5 inverts it — a *false* misconception tag on a correct answer.
- **B6. Cost meter freezes on lost/reteach turns** that generate new LLM text; per-turn `token_cost` is 0 everywhere. Reported total understates real spend. **Scenarios: S1 (T3-5), S2, S4, S6, S9.** (S7 correctly reports flat cost because those turns *are* deterministic — so behavior is inconsistent across scenarios.)
- **B7. Grading is over-strict / language-biased / non-monotonic.** Correct terse answers scored 0.0 (S7: the literal key idea); correct French scored 0.0 vs English 1.0 (S10); mastery regresses after correct answers (S5 0.325→0.125). **Scenarios: S5, S7, S10.**
- **B8. No closing summary / wrap-up at session end.** Bare `done=true` with mastery/confidence = None, no recap of learned/conceded. **Scenario: S2** (survey learner dumped).
- **B9. Reteach copy presumes confusion / is contextually wrong.** Opens with "What part felt unclear?" even after a *correct* answer (knock-on of B1/B2 but the copy itself should not presume failure). **Scenarios: S3, S6** (major); S1, S5, S7, S8, S9 (nit). After a confident *wrong* answer it asks "what confuses you?" instead of correcting (S2).
- **B10. Misconception detected but never refuted, and never retired.** Dangerous medical misconception ("mRNA alters your DNA") added to `held`, never cleared even after the learner corrects it and the concept is mastered/done; the reteach never actually rebuts it. **Scenario: S6.**
- **B11. Quiz language ignores learner language** — taught in ZH/ES/FR, quizzed in English; orientation tour in English; reteach sometimes flips to English mid-session. **Scenarios: S2, S5, S7, S10.**
- **B12. Goal-to-corpus mismatch with no disclosure** — functional/mastery goal answered by an off-target single source. **S3** (asked "how to build Raft," got a formal-verification/proofs corpus), **S5** (Black-Scholes calc → stochastic-volatility paper, no d1/d2/N(·) ever), **S6** (vaccine *design* → general overview), **S7** (asked for the *math* of attention → zero equations taught).
- **B13. Glass-box timeline/tutor_turns truncated, stale, or all-null.** **S8** (timeline stuck at 3 rows after 8 turns), **S5** (lost turns dropped from timeline), **S7** (timeline rows mis-aligned across turns), **S10** (`tutor_turns` rows all-null).
- **B14. No concede/skip escape on the keypoint flow** — repeated reteach+lost re-poses the same question indefinitely; lost turns are uncounted toward the reteach cap. **Scenarios: S6, S8, S9** (potential infinite loop). (Contrast: the *legacy* path concedes correctly — S2, S5 conceded and advanced.)
- **B15. Concede sets mastery to exactly 0.0** — below the 0.4 baseline a fresh concept starts at, so a learner who tried looks worse than one who never did. **Scenario: S10.**
- **B16. Concede rationale internally contradictory** — "mastery=0.245<0.75 or confidence=0.600<0.5" where 0.600 is not <0.5. **Scenario: S2.**

### MINOR
- **B17. Concept-count mismatch: build "map ready — N concepts" label undercounts the actual graph/route, and orphan concepts are created but never routed/taught** (stuck at 0.4 forever). **Scenarios: S2 (4 vs 6), S3 (4-route vs 8-node map), S5 (4 vs 6), S6 (4 vs 5), S7 (5-route vs 6-map), S9 (4 vs 6), S10 (says 4, has 7-8 / 5-route).** Near-universal.
- **B18. Evidence is a single boilerplate chunk reused for every concept;** `retrieve` logs "0 chunks" for new concepts yet still cites the old chunk. **Scenarios: S1, S3, S4, S6, S9, S10** (+ thin in S8). S4 is worst: the Stabilizer-Codes lesson cites GRAND text.
- **B19. Digest is non-deterministic for an identical goal** — concept names and counts differ run-to-run. **Scenarios: S2, S3.**
- **B20. Mastery starts at 0.4 with 0 observations** — unearned non-zero prior is confusing in the glass box. **Scenario: S2** (+ baseline noted in S10).
- **B21. Concept id/name instability between the events stream and `/trace`** (concept 1 = "Diffusion Models" vs "Diffusion Process"; 5 vs 7 concepts). **Scenario: S1.**
- **B22. n_observations / confidence freeze on incorrect/vague graded turns** (only update on correct), under-counting attempts. **Scenario: S7.**
- **B23. Reteach attempt counter resets** (1/2 seen twice before 2/2), so the reteach budget isn't enforced. **Scenario: S5.**
- **B24. Empty/whitespace answer silently swallowed** — no dispatch, no nudge. **Scenario: S10.**
- **B25. Bloom level stalls** — never escalates past comprehension despite 3 straight perfect answers. **Scenario: S4** (+ S1 application-level repeats).
- **B26. `decisions[]` empty on cold start and early all-correct ASSESS turns** — smooth learners see an empty rationale list. **Scenarios: S1, S4, S6, S8.**

### NIT
- **B27. Topic drift above stated level** — beginner survey quizzed on advanced concept-4 material while still on concept 1. **Scenario: S4.**
- **B28. Redundant bilingual teaching** — near-identical English then Chinese paragraphs. **Scenario: S7.**
- **B29. Running cost shown only as raw tokens, no USD per-turn** (expected on `main` per CLAUDE.md; full metering is on `feat/open-world-digest`). **Scenarios: S8, S10.**

## 3. Glass-Box Problems

- **Routing/decision rationales are the standout and are trusted in every scenario** — `route_decider` cites exact thresholds ("ADVANCE concept 6: mastery=0.858>=0.75, confidence=0.900>=0.5"), shows reteach attempt N/2 + strategy, and the `recommend` list flags eligible/blocked with "unlocks N concepts." This is the project's best explainability asset (S1, S3, S4, S5, S6, S7, S8, S9, S10).
- **But the trace contradicts itself or under-reports in 6 ways:** truncated/stale timeline (S8), dropped lost turns (S5), mis-aligned answer/score/decision rows (S7, S10), all-null `tutor_turns` (S10), null concept-name on decision rows reading "reteach / null" (S10), and self-contradictory concede rationale (S2, B16).
- **Cost glass box is incomplete:** per-turn `token_cost` is 0 across the board; total freezes on reteach/lost generations (S1, S2, S4, S6, S9). Cannot reconcile displayed total with real spend.
- **Misconception layer is dead weight on the keypoint path** — `held_misconceptions`/`detected_misconception` never populate (S1, S2, S4, S7, S8, S9, S10), populate falsely (S5), or populate but never retire (S6). The advertised misconception model is effectively inert live.
- **Evidence pane is decorative** — single reused chunk, "0 chunks" retrieves still cite stale evidence, wrong-concept citations (S4). Citations look grounded but aren't concept-specific.
- **Concept-identity / count instability** between events vs trace and map-label vs route (S1, S2, S3, S5, S6, S7, S9, S10) makes it hard to reconcile which node is which.

## 4. Edge-Case Handling Summary

| Input | Verdict | Detail |
|---|---|---|
| **"I'm lost" (literal)** | **Excellent, universal** | Classified `action=lost`, routed to `handle_lost`, re-explained with a fresh strategy, **no mastery penalty** — in all 10 scenarios. The standout feature. |
| **"I don't know" (literal)** | **Excellent** | Same `lost` path; advances the strategy ladder (analogy→worked_example→contrast). Note: not distinguished from confusion (S7) — an honest "don't know" is treated as being lost. |
| **Clearly-wrong answer** | **Mixed** | Correctly scored 0.0 and reteached (S1, S4, S6, S9), but the **misconception is never named/recorded** (S2, S3, S4, S7, S9, S10), and on the keypoint flow a wrong answer can silently advance/concede with no learner-visible failure signal (S3 T3). |
| **Vague/partial answer** | **Poor — no partial-credit band** | Grading is binary. Over-rewarded once (S1: hedge → 1.0), but elsewhere a directionally-correct gist scores a hard 0.0 with the same ~0.2 penalty as a fully-wrong answer (S4, S5, S6, S7, S9). Undermines trust. |
| **Empty / whitespace** | **Silently swallowed** | No dispatch, no "please type something" nudge; prior question re-shown (S10). |
| **Loop safety** | **Path-dependent** | Legacy path concedes after exhausting reteaches and never loops (S2, S5). **Keypoint path has no concede/skip escape** — re-poses the same question 4× and lost turns don't count toward the cap (S6, S8, S9), so a stuck learner can loop indefinitely. |
| **Recovery** | **Works** | After a wrong+lost+idk streak, strong answers climb mastery back over threshold and advance (S1, S4, S6, S7, S9) — *when grading isn't inverted*. |

## 5. What Worked Well

- **Cold-start build choreography (universal praise, all 10).** Streamed `discover → discover_done → digest → map → teach` stages, each naming the real source paper and method, plus an inline concept-map SVG and a narrative ORIENT tour. Makes the ~30-90s wait feel productive and transparent — no blank spinner.
- **Adaptive reteach strategy ladder (all 10).** `direct → analogy → worked_example → contrast`, with genuinely distinct, on-topic, beginner-appropriate explanations (rolling ball with drift S1, cafeteria buffet S8, recipe/sandwich S6/S9). The contrast strategy sometimes nails the exact misconception (S8, S9).
- **Glass-box routing rationales (all 10).** Threshold-explicit, human-readable ADVANCE/RETEACH/LOST/CONCEDE strings; the strongest explainability feature and faithful to the "rule-computed, not model-emitted" contract (S8 even surfaces "never LLM self-judge").
- **Lost-handling pedagogy (all 10).** Confusion is treated as a help request, not a failure — no mastery penalty. Correct call.
- **Dual-threshold advance gate** (mastery≥0.75 ∧ confidence≥0.5, ≥2 observations) is principled and legible; route flips pending→done and auto-selects the prereq-correct next concept (S1, S4, S6, S7, S8, S9).
- **Prereq-ordered DAG progression** unlocks concepts in dependency order (S1, S2, S4, S8).
- **Concede safety valve on the legacy path** prevents infinite loops (S2, S5).
- **Bilingual teaching bodies** are fluent and on-topic in ZH (S2, S7) and FR (S10) — the *teaching* localizes even though quizzes don't.
- **Ran end-to-end on the live path with no crashes** in every scenario.

## 6. Cross-Scenario Patterns

**Language handling (ZH S2/S7, ES S5, FR S10).** Consistent split-brain failure: **teaching bodies localize correctly, but quiz questions and the orientation tour are always English, and reteach sometimes flips to English mid-session** (S5, S7). Worse, **grading is English-keyword-biased** — a correct French answer scored 0.0 where its English twin scored 1.0 (S10). A non-English learner gets a jarring bilingual mishmash and is penalized for answering in their own language. This is a coherent, fixable cluster: localize question generation + reteach, and make the grader language-agnostic (grade the key idea, per CLAUDE.md).

**Survey vs mastery vs functional depth.**
- **Survey (S2, S4, S8, S10):** best fit overall (S8 = the only 4), but suffers orphan/un-routed concepts (B17) that defeat "give me an overview," topic drift above "basics" (S4), and abrupt no-summary endings (S2).
- **Mastery (S1, S5, S7):** worst-served. Demands depth and completion, but binary/over-strict/inverted grading makes the advance threshold hard or impossible to reach (S5, S7), and the misconception layer central to "deep mastery" never fires.
- **Functional (S3, S6, S9):** consistently hit **goal-to-corpus mismatch** (B12) — "how do I build/apply X" answered by a theory/overview/verification corpus with no disclosure. The single-source corpus can't satisfy an implementation intent, and the tutor never says so.

**Cold-start UX (all 10).** Uniformly the strongest moment of the product: staged build telemetry + named real source + SVG map + ORIENT tour. The one recurring blemish is the **map-label concept count being wrong** (B17, 7 of 10 scenarios) and **id/name instability** between the events stream and `/trace` (S1) — the first thing a learner reads is an inaccurate count, and orphan concepts shown on the map are never reachable, over-promising the curriculum.

**Meta-pattern.** The legacy path (concede, loop-safe) and the keypoint path (no escape hatch, dead misconception layer, repeated questions) diverge sharply — most of the major UX failures are concentrated on the newer keypoint flow, while the glass box, cold start, and lost-handling are shared strengths. Fixing **B1 (grading), B2 (feedback event), B4 (question variation), B5 (misconception population), and B14 (keypoint concede)** would lift the median scenario from ~3 to the S8-level 4.