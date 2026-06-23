# LitNavigator — Live Tutor QA Report

10 testers, 10 live scenarios (~115 answer-turns total), driven via `drive_session.py` against the running server at `127.0.0.1:8000`.

Scenario index:
- **S1** ML/diffusion (EN, mastery) — rating 4
- **S2** CRISPR (Chinese, survey) — rating 3
- **S3** Raft consensus (EN, functional) — rating 3
- **S4** QEC (EN, survey) — rating 4
- **S5** Black-Scholes (Spanish, mastery) — rating 3
- **S6** mRNA vaccines (EN, functional) — rating 4
- **S7** Transformer self-attention (Chinese, mastery) — rating 2
- **S8** Behavioral economics/nudges (EN, survey) — rating 4
- **S9** RLHF (EN, functional) — rating 4
- **S10** Graph neural nets (French, survey) — rating 2

---

## 1. Overall Usability

**Average rating: 3.3 / 5** (4×rating-4, 3×rating-3, 2×rating-2; no 5s, no 1s).

**Holistic read:** The product has a genuinely strong pedagogical core — adaptive Bloom-leveled quizzing, strategy-rotating reteach, humane "lost" handling, and a transparent decision glass box — and it never crashed in 9 of 10 runs. When the corpus matches the goal and the language is English, the experience is good (S1, S4, S6, S8, S9 all rated 4). But three structural weaknesses drag the average down and produced the two rating-2 sessions (S7, S10): (a) non-English sessions get a broken bilingual experience, (b) the keypoint flow can fail to actually advance through the route, and (c) the glass box — the competition's headline feature — is riddled with off-by-one and metering bugs that make the audit trail untrustworthy.

**The 3 things that hurt most:**

1. **Progression failures on the keypoint path (blocker).** S7 and S10 never got past concept 1 of 4. In S7 `advance_kp` fired but re-taught concept 1's content; in S10 the grader stayed locked to concept 1's rubric and marked answers about *other* concepts "correct." The learner's actual goal (QKV math in S7, GNN basics in S10) was never reached and the session could never reach `done`. S3 is a softer version: it completed, but the one build-relevant concept the learner asked for was excluded from the route.

2. **Glass-box trace is misleading.** A timeline off-by-one/-N decision misalignment appears in **S1, S2, S3, S8, S9** — wrong answers (score 0.0) are shown as `decision=advance`/"Concept mastered," and correct answers shown as `reteach`. This is the single most-cited bug and it directly undermines the trace a competition judge would read.

3. **Non-English language inconsistency.** Every non-English scenario (**S2, S5, S7, S10** — Chinese, Spanish, Chinese, French) posed **all quiz questions in English** regardless of session language. S2's final study artifact came out in **Bengali**; S5 leaked a **Hebrew** word into Spanish feedback and reverted "lost" handling to English.

---

## 2. Consolidated BUG List (deduped, ranked by severity then frequency)

### BLOCKER
| # | Bug | Scenarios | Notes |
|---|-----|-----------|-------|
| B1 | **Session never progresses past concept 1** — keypoint loop re-teaches/re-asks concept 1; goal unreachable, `done` never true | S7 (1), S10 (1) | S7: `advance_kp` fires but content stays concept 1. S10: grader locked to concept-1 rubric, marks other-concept answers correct |
| B2 | **Intermittent SQLite hard failure at cold start** — `[error] bad parameter or other API misuse` leaves empty/partial route, unusable session | S6 (1) | Reproduced 2 of ~5 starts; first-timer sees error + blank tutor |

### MAJOR
| # | Bug | Scenarios | Notes |
|---|-----|-----------|-------|
| M1 | **Timeline decision/score misaligned (off-by-one/-N)** — wrong answers labeled `advance`, correct answers labeled `reteach` | S1, S2, S3, S8, S9 (5) | Most frequent bug; corrupts the audit trail |
| M2 | **Comprehension-tier quiz question recycled from concept 1** across later concepts (recall/application are fine) | S2, S4, S5, S6, S8(nit), S9, S10 (6–7) | Off-topic assessment for the concept being "mastered" |
| M3 | **Quiz questions emitted in English for non-English sessions** | S2, S5, S7, S10 (4) | All non-English scenarios |
| M4 | **Concepts 2–4 taught/assessed with 0 retrieved chunks**; only concept 1 ever cited (single chunk c0) | S1, S2, S3, S4, S5, S6, S8, S9 (8) | "cited-evidence retrieval" returns nothing for most of route; near-universal |
| M5 | **Cost not metered on reteach / handle_lost LLM turns** — total frozen across real re-explanations | S1, S2, S4, S5, S6, S7 (6) | Displayed total understates spend |
| M6 | **Lenient/uncalibrated grader on vague answers** — hand-wavy answers graded fully correct, sometimes bigger mastery jump than precise answers | S3, S4, S6 (3) | S3: vague +0.21 vs precise +0.075 |
| M7 | **Same quiz question re-posed verbatim across consecutive reteach/lost turns** (3–5×) | S1, S3, S7, S9, S10 (5) | Strategy varies, prompt doesn't — reads as stuck loop |
| M8 | **Topic-loose / wrong-rubric grading false positives** — answers graded against wrong keypoint, praised for untaught terms | S7, S10 (2) | Tied to B1 progression bugs |
| M9 | **Goal not served** — functional/build goal answered with theory-only route; build concept excluded | S3 (1) | "Reference implementations" in map but not route |
| M10 | **Off-target / too-advanced source accepted** for a survey/intro goal | S10 (1) | MECCH (niche HGNN paper) for "intro to GNNs" |
| M11 | **Trace route ↔ event-stream route disagree** (4 vs 6/7 concepts, different names); cold start non-deterministic | S7, S10 (2) | Same goal → different concept sets across runs |

### MINOR
| # | Bug | Scenarios |
|---|-----|-----------|
| m1 | **`[done]` event reports NEXT concept's defaults (0.4/0.0)** after an advance → looks like mastery regression to the learner | S1, S2, S3, S6, S8 (5) — the live "flat bars" bug class |
| m2 | **`detected_misconception`/`held_misconceptions` never populated** on keypoint path even on textbook misconceptions | S1, S2, S6, S9 (4) |
| m3 | **Detected misconception never cleared** after correction + mastery | S4, S8 (2) |
| m4 | **Concept-map node count mismatch / orphaned nodes** — map shows 5–8, route covers 4; extras never taught | S1, S3, S4, S5, S7, S10 (6) |
| m5 | **Timeline / tutor_turns under-logs turns** (lost turns omitted; 3–6 rows for 9–16 turns) | S1, S3, S4, S7, S10 (5) |
| m6 | **Route claims full mastery while dropping mapped concepts** ("4 of 4" but 3 of 7 never taught) | S5, S8(via m4) (1–2) |
| m7 | **Hard 0.0 on vague-but-gist-correct answer** (opposite of M6; grader inconsistent) | S8 (1) |
| m8 | **Hebrew word leaked into Spanish feedback** ("בדיוק") | S5 (1) |
| m9 | **Final study artifact in wrong language** (English for Spanish session) | S5 (1) — see B-level Bengali case in S2 |

### NIT
- Reteach opens with an unanswerable meta-question ("which part felt unclear?") then immediately re-teaches — S1, S5
- `tutor_turns` mislabels turn_type (graded turn → "teach"; Bloom level stored in `strategy` field) — S7, S10
- `concepts[].status` null even when route says "done" — S1
- Concept-map SVG draws nodes but no prereq edges/arrows — S10
- Cost never surfaced in learner-facing events (only state/trace) — S7

---

## 3. Glass-Box Problems

The decision-rationale strings themselves are excellent and trusted everywhere (e.g. "ADVANCE concept 1: mastery=0.768≥0.75 (goal ceiling), confidence=0.900≥0.5 (≥2 correct observations)"). The problems are in the trace plumbing:

- **Timeline misalignment (M1)** — the headline glass-box defect; answers paired with the wrong turn's decision in S1, S2, S3, S8, S9. Makes "wrong answer → advanced" appear in the trace.
- **Per-step cost is non-functional** — `token_cost=0` on every `tutor_turns` row in S1, S5, S6, S7, S10 even as the session total rises; reteach/lost LLM work is never metered (M5).
- **Under-logging** — lost turns and many graded turns absent from `timeline`/`tutor_turns` (S1, S3, S4, S7, S10); the trace is not a faithful record.
- **One-turn lag** — `decisions`/`evidence`/`timeline` empty at cold start and lag the event stream by a turn (S3, S4, S7, S9, S10); mid-turn the rationale panel is blank.
- **`decision`/`why_sentence` null in the per-turn `state` event** the UI consumes (S1, S4, S5, S7, S9) — rationale only lives in `trace.decisions`, so the live UI shows `decision=None`.
- **Single-chunk evidence (M4)** — `evidence` never grows beyond c0/c1; no per-concept grounding.
- **Trace ↔ event route disagreement & non-determinism (M11)** in S7, S10.
- **`done` payload shows next concept's defaults (m1)** — would crash a UI mastery bar bound to it (S1, S2, S3, S6, S8).
- **`induced_edges` empty / prereq DAG has no edges** — S3's `recommend[]` shows "unlocks 0 concepts" for all; the "concept map" is a linear list dressed as a DAG.

---

## 4. Edge-Case Handling Summary

Strong and consistent across all 10 scenarios — this is a clear product strength.

- **"I'm lost" (literal):** Correctly classified `action=lost` → `handle_lost` in **all 10**. No mastery penalty; re-explains from a fresh angle. (S1, S2, S3, S4, S5, S6, S7, S8, S9, S10)
- **"I don't know" (literal):** Routed identically to "lost" in **all 10**; consistently rotates to a *different* strategy than the prior lost turn (analogy → worked_example → contrast). S2 and S9 even named the misconception on the idk turn (best teaching moments).
- **Clearly-wrong / misconception:** Graded incorrect with specific, accurate rebuttals everywhere; mastery drops sensibly (typically to 0.075–0.1). **Caveat:** the misconception is rarely *tagged* in the model — `detected_misconception` populated only in S4; null in S1, S2, S6, S9 (m2).
- **Vague/partial:** **Inconsistent — the main edge-case weakness.** Correctly rejected with specific feedback in S1, S5, S7, S10; but graded *fully correct* in S3, S4, S6 (M6), and conversely a hard 0.0 on a gist-correct answer in S8 (m7). Grader calibration on vague input is the unreliable axis.
- **Recovery:** Worked in every scenario that exercised it (S1, S4, S5, S6, S7, S9, S10) — dual-threshold advance (mastery ≥ 0.65/0.75 AND ≥2 correct observations) is recoverable, not a dead end. **Caveat:** S2 noted the 2/2 reteach cap has no concede/escape — a stuck learner can loop on one keypoint indefinitely.
- **Out-of-corpus probe:** S8's post-completion "what about loss aversion?" got an honest refusal ("I can teach the listed concepts, but not loss aversion") with no hallucination — the boundary feature works.

---

## 5. What Worked Well

1. **Cold-start narration** (cited in all 10) — staged `discover → digest → map` build events with method/paper labels + inline SVG concept graph make the 30–90s wait feel productive, not a dead spinner.
2. **Adaptive pedagogy** — Bloom ladder (recall → comprehension → application, drops on failure) and strategy-rotating reteach (direct → analogy → worked_example → contrast) are real, visible, and well-pitched (S1, S3, S4, S6, S9). Analogies are concrete (recipe card/wanted poster, cafeteria, shopping list with a leader).
3. **Decision rationales** — quantitative, human-readable, fully transparent thresholds; trusted in every scenario even where the trace plumbing around them is buggy.
4. **Specific feedback** — names the exact error on wrong answers and accepts correct paraphrases (S1, S3, S6, S9); quotes the learner's own words back, in-language for feedback (S5, S10).
5. **Edge-case empathy** — no-penalty "lost"/"idk" with rotating strategies; honest out-of-corpus boundary (S8).
6. **Stability & completion** — 9/10 ran end-to-end with no crashes; the completing English sessions (S6, S9, and S2/S5 despite language bugs) produced clean "N of N mastered" closure + downloadable Cornell-style study artifacts.
7. **Cited, grounded teaching** on concept 1 — real source text attached to teach/feedback (weakened only by the single-chunk M4 issue downstream).

---

## 6. Cross-Scenario Patterns

**Language handling (Chinese S2/S7, Spanish S5, French S10):** Systematically half-localized. Teaching prose and feedback localize (often bilingually); **quiz questions are always English** (M3, all 4). Deeper failures compound: S2's final artifact rendered in **Bengali**, S5 leaked **Hebrew** into Spanish and reverted lost-handling + artifact to English, S7/S10 cold-start route was English then a second teach in the target language. **Net: a non-English learner gets a jarring multi-language mishmash, and the headline deliverable (artifact/quizzes) is frequently not in their language.** This is the clearest driver of the two rating-2 scores (S7, S10 both non-English) and the two rating-3s among them (S2, S5).

**Survey vs mastery vs functional depth:**
- **Survey (S2, S4, S8, S10):** The per-concept multi-question gate is arguably too heavy — a "quick overview" (S2's 快速概览) still needs 2–3 correct answers per concept. S4/S8 worked well; S2/S10 were dragged down by language/source bugs, not depth mismatch per se.
- **Mastery (S1, S5, S7):** Pacing is the risk. S1 took 7 turns to clear concept 1 (by design, via failures) but the deep goal exposes the slow single-correct-answer nudge (+0.07). S7 catastrophically failed to reach the deep QKV math the learner wanted.
- **Functional/build (S3, S6, S9):** S9 (RLHF) and S6 (mRNA) served the goal well; **S3 (Raft) did not** — a "build a working implementation" goal got a theory-only route with the build concept excluded (M9). Functional goals that imply *doing* rather than *understanding* are not reliably scoped.

**Cold-start UX:** Uniformly the best-reviewed surface — narrated build stages + SVG map in all 10. But three recurring cold-start defects sit underneath the good narration: the **concept-count label is frequently wrong** (m4: "4 concepts" with 5–8 in the map, in S1/S3/S4/S5/S7/S10), the **map is non-deterministic** (S7, S10 produce different concept sets per run), and cold start is where the **only hard crash** lives (B2, S6). So the wait *feels* trustworthy while the artifact it produces is often inconsistent with itself.