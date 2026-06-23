I have all the per-scenario reports. Let me synthesize them into the QA report. No tools needed — this is pure analysis of the provided data.

# LitNavigator — Live Tutor QA Synthesis

10 testers, 10 live open-world tutor scenarios (cold start + 8–10 driven turns each). Scenarios span 6 English, 2 Chinese (#2 CRISPR, #7 Transformers), 1 Spanish (#5 Black-Scholes), 1 French (#10 GNNs); intents split across mastery, survey/overview, and functional ("how do I build/apply").

---

## 1. Overall Usability

**Average rating: 3.6 / 5** (ratings: 4,4,4,2,4,4,3,4,4,3 → s1 4, s2 4, s3 4, s4 QEC 2, s5 4, s6 4, s7 3, s8 4, s9 RLHF 4, s10 3).

**Holistic read:** The product is genuinely good on its core loop — cold-start narration, adaptive reteach pedagogy, fair specific feedback, and a legible decision trace. Every tester praised the same three pillars: narrated cold start, the lost/don't-know recovery path, and human-readable advance/concede rationales. The score is dragged down by a consistent set of cross-cutting defects (citations, question/keypoint desync, no exit from a stuck keypoint) rather than by any single broken scenario. The two low outliers are instructive: **#4 (QEC, 2/5)** is the worst case of the question-drift + single-concept-stall bugs combining into a session where correct answers were marked wrong; **#7 (3/5)** and **#10 (3/5)** are dragged down by the glass-box off-by-one bug and language inconsistency respectively. No non-English scenario scored above 4, and all three non-English testers flagged language inconsistency as their most jarring issue.

**The 3 things that hurt most:**

1. **Degenerate evidence / single-chunk citations.** Every tester (10/10) reported that one generic chunk `c0` from paper 1 is cited for every concept and every turn, while `retrieve` logs "0 chunks" for later concepts yet still attaches `c0`. DISCOVER finds 2–3 real sources but only the first is ever taught from. The glass-box "cited evidence" promise is effectively non-functional.
2. **Getting trapped on one keypoint with no exit.** Multiple scenarios (#1, #3, #4, #6, #7, #8, #10) stall on a single keypoint for 4–6 consecutive turns, re-posing a near-identical or byte-identical question with no Bloom de-escalation, skip, or "move on" option after repeated lost/reteach signals. #4 never escaped concept 1 across the whole 8-turn session.
3. **Question/keypoint desync and timeline off-by-one in the glass box.** The active keypoint and the quizzed keypoint diverge (#1, #2, #4, #8, #9, #10), and the timeline binds each answer to the *next* turn's decision (#2, #3, #7) — most damagingly in #7/#4 where a clearly-wrong answer is labeled "advance / Concept mastered." This actively misleads and undermines trust.

---

## 2. Consolidated BUG List (deduped, ranked by severity then frequency)

### MAJOR

| # | Bug | Scenarios (freq) |
|---|-----|------------------|
| B1 | **Non-concept-specific evidence / single stale chunk `c0`.** Same generic chunk cited for all concepts/turns; `retrieve` logs "0 chunks" for later concepts but `c0` is still attached; discovered sources 2/3 never taught from. | #1, #2, #3, #4, #5, #6, #7, #8, #9, #10 (10/10) |
| B2 | **Question / keypoint desync.** Quiz question posed for the wrong keypoint/concept — often loops back to an already-mastered concept while rationale names the new keypoint. | #1 (concept2→quizzes concept1), #2, #4, #8, #9 (comprehension template leak), #10 (8/10 turns) |
| B3 | **Stuck on one keypoint, no exit.** After repeated reteach + lost signals, no Bloom de-escalation, skip, or concede; question re-posed near-verbatim. | #1, #3, #4, #6 (4 turns), #7, #8, #10 (6 turns) |
| B4 | **Timeline off-by-one.** Each answer row tagged with the *following* turn's decision; a wrong answer can display "advance / Concept mastered." | #2, #3, #7 (worst), #4 (implied via drift) |
| B5 | **Quiz-question language ignores learner language.** Non-English goal yields English-only quiz questions; lost/reteach re-explanations also revert to English. | #2 (CN), #5 (ES), #7 (CN), #10 (FR) (4/4 non-English) |
| B6 | **Grader over-credits vague/hand-wave answers.** A vague reply scored 1.0 (full), sometimes out-scoring a precise answer. | #3, #7 (vague +0.21 > precise +0.075), #9 |
| B7 | **Question drift vs grading target (QEC).** Posed question silently shifts scope so correct on-domain answers are graded wrong against an unrelated keypoint. | #4 (T7, T8) |
| B8 | **Single-concept stall / survey breadth not delivered.** 8-concept map promised but session never leaves concept 1 (which concept 2 merely rewords). | #4 (whole session) |
| B9 | **"done" event reports next concept's reset mastery (0.4/0.0).** Headline mastery appears to crash right after a successful advance. | #6, #9 (also noted #5, #8 as panel/feedback variants) |
| B10 | **Feedback mastery_before/after contradicts learner panel.** Two mastery readouts shown to the learner disagree (e.g. feedback 0.3→0.1 vs panel 0.4→0.685). | #8 |

### MINOR

| # | Bug | Scenarios (freq) |
|---|-----|------------------|
| B11 | **Per-step `token_cost` always 0** in `decisions[]` and `tutor_turns[]` while session total grows — cost not attributable to any step. | #2, #4, #5, #6, #7, #8, #9 (7/10) |
| B12 | **Quiz question text repeats verbatim** across reteach/lost turns while only the explanation varies — looks like a broken record. | #1, #2 (~5×), #3, #5, #7, #9 |
| B13 | **Misconception never persisted.** Textbook misconception named in prose but `detected_misconception` stays null and `held_misconceptions` stays []. | #1 (GAN), #2 (gRNA cuts), #5, #6 (DNA edit), #7, #10 (equivariance) |
| B14 | **Lost-path generation appears unmetered.** Token total flat across substantive lost re-explanation turns. | #8, #9 |
| B15 | **`trace.timeline` empty / frozen.** Empty across all turns in keypoint flow (#1); frozen at 3 rows after 8 turns (#7); empty on cold start until a reteach fires (#9, #10). | #1, #7, #9, #10 |
| B16 | **Partial answer graded hard 0.0** with no partial credit despite feedback acknowledging it is partly correct. | #10 (also #4 noted harshness) |
| B17 | **Reteach question over-scaffolded** — nearly states the answer, undermining it as assessment. | #5, #8 |
| B18 | **Confidence one-directional** — does not drop after a clearly wrong answer (held at 0.6). | #3, #9 (also #10: sticky/coarse confidence) |
| B19 | **Mastery scale under-credits demonstrated knowledge** — conceded concept lands at 0.245 despite multiple correct statements. | #4 |
| B20 | **`decisions[].step` always null** — decision panel can't name which node made each call. | #7 |
| B21 | **Cold-start build SSE events carry empty text** — no progress message during the long wait. | #7 (note: contradicts the well-narrated cold start in all 9 other scenarios — appears scenario/run-specific). |

### NIT

| # | Bug | Scenarios |
|---|-----|-----------|
| B22 | Bloom label mismatch between question event (`bloom_level`) and recorded `tutor_turn` strategy. | #1 |
| B23 | `route` "reason" frozen at "Initial route from concept DAG." even for completed/reordered steps. | #2, #5 |
| B24 | Displayed mastery starts 0.4 but first grade reports `mastery_before: 0.3` (internal BKT prior leaks). | #3, #9 |
| B25 | Concept map non-deterministic across identical goals (3 runs, 3 graphs). | #4 |
| B26 | Awkward/circular yes-no auto-generated questions that leak the answer. | #5 |
| B27 | No fast-forward / "I already know this" option; advance needs ≥3 correct, slow for confident learners. | #4, #6, #8, #10 |
| B28 | Cold start emits two teach blocks back-to-back (English overview + French paragraph). | #10 |

---

## 3. Glass-Box Problems

The glass box is the project's signature feature and is the **best** part when it works (every tester praised the advance/concede rationale strings with quantitative thresholds, e.g. "mastery=0.855≥0.75, confidence=1.000≥0.5. Concept mastered."). But the structured trace is unreliable:

- **Citations are pro-forma, not grounding** (B1) — the most damaging glass-box failure. One chunk reused everywhere; `concept_id` often null (#7, #10); retrieval returns 0 chunks but a citation still shows.
- **Timeline is the least trustworthy panel:** empty/frozen (B15) and off-by-one (B4) — in #7 it labels a wrong answer "Concept mastered."
- **Cost attribution is opaque** (B11, B14): per-step `token_cost` always 0; lost-path turns sometimes unmetered; `total_token_cost` shown as bare tokens with no USD in the trace endpoint even though the live STATE event carries USD (#1, #7, #9, #10) — the two surfaces disagree.
- **Misconception map is inert** (B13): a headline "induction/misconception" capability that recorded nothing in 6 scenarios where a textbook misconception was explicitly named in prose.
- **Keypoint-flow decisions are partial:** ASSESS Bloom/keypoint choices live only in a free-text `rationale` string, not in `decisions[]`; `decisions[].step` null (#1, #7).
- **Concept `status` null** while route status lives only on the route array — a UI reading `concept.status` gets nothing (#7).
- **Route reason static** ("Initial route from concept DAG.") and **route exposes only 4 of 8 concepts** with no explanation of the other 4 (#2, #3, #5, #7, #10).
- **First-paint glass box looks broken** — `decisions`/`timeline`/`tutor_turns` are bare `[]` on cold start with no empty-state signal (#6, #9, #10).

---

## 4. Edge-Case Handling Summary

| Case | Verdict | Notes |
|------|---------|-------|
| **"I'm lost" (literal)** | **Excellent (10/10).** | Classified as `action=lost`, routed to `handle_lost`, NOT graded, **zero mastery penalty**, fresh re-explanation each time. Unanimous win. |
| **"I don't know" (literal)** | **Excellent (10/10).** | Same lost path, and usually a *distinct* second strategy (worked_example→contrast). Caveat: indistinguishable from "I'm lost" in the glass box (#6) — both `from_node=handle_lost`. |
| **Clearly wrong (misconception)** | **Good.** | Correctly graded false, mastery drops, feedback **names and refutes the specific misconception** (the single most-praised feature, #1). Gap: misconception never persisted to learner model (B13). |
| **Vague / partial** | **Inconsistent — the weak spot.** | Sometimes correctly rejected with "too vague" (#1, #2, #5, #6, #8); but sometimes graded **fully correct 1.0** (#3, #7, #9) — occasionally out-scoring a precise answer (#7). And sometimes **hard 0.0 with no partial credit** despite partly-correct feedback (#10). Three different behaviors for the same input class. |
| **Off-topic-but-fluent** | **Good (#2).** | Correct guide-RNA answer to a PAM question was rejected — grader not fooled by fluent-but-irrelevant content. |

**Recovery** works end-to-end in every scenario: a learner driven down to ~0.075 mastery can climb back and cleanly advance via the dual threshold. The lost path never permanently traps or punishes (the *question* repetition does, B3/B12 — support is in the explanation, not the difficulty).

---

## 5. What Worked Well

1. **Narrated cold start (9/10).** Staged SSE build events (discover → real source titles with type labels → digest → per-concept ticks → "Concept map ready — N concepts" + inline SVG DAG) make the 30–90s wait feel like progress, not a hang. (Only #7 saw empty build text.)
2. **Lost / don't-know recovery (10/10).** First-class help-request path, no penalty, genuine fresh-angle re-explanation — universally cited as a standout.
3. **Adaptive reteach strategy ladder (10/10).** Visible, real rotation: direct → analogy → worked_example → contrast, with good domain analogies (fogging a window, coworkers + shared notebook, soup taste-testing, boat-in-the-sea).
4. **Specific, paraphrase-tolerant feedback.** Names the missing key idea, refutes the exact misconception, accepts correct paraphrases. Grades the key idea, not verbatim — exactly the project's stated principle.
5. **Legible advance/concede rationales.** Quantitative dual-threshold strings ("mastery=0.768≥0.75, confidence=0.900≥0.5, ≥2 correct observations. Concept mastered.") — the most-praised glass-box element.
6. **Rising Bloom ladder within a concept** (recall → comprehension → application → analysis/synthesis), resetting per concept; well-written scenario-style stems.
7. **Sensible mastery movement with tier labels** (Seen/Familiar/Solid/Mastered) — up on correct, down on wrong, flat on lost.
8. **DISCOVER relevance gate** found real, on-topic sources with no wrong-sense matches (notably #3 Raft: Wikipedia + "Raft Refloated" + an academic analysis).
9. **Prereq-gated recommend cards** ("Ready now — unlocks 2 concepts" / "Blocked — needs X first") give plain-language why-this-next guidance (where DAG edges exist — see cross-pattern below).

---

## 6. Cross-Scenario Patterns

**Language handling (CN #2/#7, ES #5, FR #10):** Consistent, systematic split. **Teaching prose and grading feedback honor the learner's language** (fluent Chinese/Spanish/French, domain-correct). But **quiz questions, the ORIENT/overview block, and — worst — the lost/reteach re-explanations revert to English.** #7 and #10 both flagged the cruelest case: the lost-handler switches to English *exactly when the learner is most confused*. #10 also emits two teach blocks (EN overview + FR paragraph) at cold start. Net: the happy path localizes, the assessment and recovery paths do not. This is the single biggest non-English UX defect and affects 4/4 non-English scenarios (B5).

**Survey vs mastery vs functional depth:** **Intent does not modulate pacing.** Survey/overview goals (#2 CRISPR "quick overview," #4 QEC "basics," #8 behavioral econ "overview," partly #10 FR "introduction") are forced through the same full per-concept mastery loop — ≥2–3 correct answers to cross the 0.65/0.75 ceiling per concept — as mastery goals (#1, #5, #7). No lighter "tour" path is offered. #4 is the extreme failure: a "basics" request that never left concept 1. Functional goals (#3 Raft, #6 mRNA, #9 RLHF) got accurate build-oriented worked examples and read as the best-fit intent, but still ran the same mastery gate. **Recommendation surfaced by testers:** a survey/tour mode with single-pass coverage and no 2-correct gate; a fast-forward / "I already know this" affordance (B27).

**Cold-start UX:** Uniformly strong (9/10) and the most reliable positive. The pattern: staged streamed events + real source titles + inline SVG concept map. Failure modes are narrow: #7 emitted empty build-event text (silent wait), and #10 took 62.6s (long but well-narrated). No tester saw a dead spinner except #7. First-paint *glass box* (not the build panel) does look empty until the first decision fires (#6, #9, #10) — an empty-state placeholder would close that gap.

**Two structural patterns worth flagging beyond the above:**
- **Route covers only 4 of 8 induced concepts** in most scenarios (#1, #3, #4, #5, #7, #10) with no explanation to the learner of the other 4 — combined with **flat prereq DAGs** (#3, #6 show every concept as "unlocks 0 concepts" / all prereqs None, no edges drawn) the "each concept builds on the last" claim is often not reflected in the actual graph structure.
- **The newest keypoint (ORIENT→TEACH→ASSESS) path is where most MAJOR bugs live** — B2/B4/B7/B13 (desync, timeline off-by-one, question drift, missing misconception persistence) are keypoint-flow defects; the offline milestone gates only cover the legacy path, so these are exactly the live-only bugs the LIVE gates exist to catch.