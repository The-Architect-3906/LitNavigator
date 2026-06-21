# Inner-loop (LangGraph tutor) live validation — 10 scenarios × learner variants

**Date:** 2026-06-21 · **Branch:** `feat/open-world-digest` · **Harness:** `litnav/evaluation/inner_loop_scenarios.py`
**Per-scenario logs:** [`e2e-logs/innerloop-*.md`](e2e-logs/) · **Data:** [`e2e-logs/innerloop-summary.json`](e2e-logs/innerloop-summary.json)
**Provider:** OpenAI live · strict mode · every call metered.

## What this validates
The earlier 10-scenario e2e exercised the stages *individually* (discover → digest → one grade → artifact).
This drives the **real compiled LangGraph tutor** turn-by-turn on **freshly-digested open-world graphs**:
`goal_elicit → planner → orient → select_next → retrieve → teach_kp → assess_next → grade_kp →
{reteach_kp | advance_kp | concede} → select_next → … → done`, with an interrupt/resume loop and a
**scripted learner persona** per scenario that answers the *actually-posed* quiz (a "correct" answer uses
the quiz's real `answer_key`, so `grade_kp` does genuine grading).

### Learner personas (each exercises specific branches)
| persona | answer policy | branch under test |
|--|--|--|
| `mastery` | always the real answer_key | teach → assess → grade(correct) → **advance** → done |
| `struggle` | wrong once per keypoint, then correct | grade(wrong) → **reteach_kp** → recover → advance |
| `give_up` | always wrong | reteach exhausted → **concede** honestly |
| `lost_then_recover` | signal "lost" once → then correct | assess → **handle_lost** (re-explain) → recover |

Matrix: 1 diffusion·mastery · 2 CRISPR(中)·struggle · 3 raft·give_up · 4 QEC·lost_then_recover ·
5 black-scholes(es)·mastery · 6 mRNA·struggle · 7 attention(中)·mastery · 8 nudges·give_up ·
9 rlhf·struggle · 10 GNN(fr)·lost_then_recover.

## Bug this validation found and fixed
Building the harness surfaced a **release-blocking** bug invisible to the unit gates:

- **Bloom-ceiling infinite re-quiz.** For goals whose Bloom ceiling is below `application`
  (`survey`→comprehension, also `functional`), `assess_decider` kept returning `assess_next` to upgrade
  Bloom; `assess_next` capped at the ceiling and re-posed the *same* question — so the concept **never
  advanced**. A survey run looped the full 40-turn cap with every route step stuck `pending`. Only
  `mastery` goals (ceiling = ladder top) advanced. **Fix** (`grade_kp.assess_decider`): stop upgrading at
  the ceiling and run the concept-level mastery check. After the fix the QEC survey run went **40 turns →
  13**, **all `pending` → all `done`**, **$0.032 → $0.019**. Regression test: `tests/test_bloom_ceiling_advance.py`.
- (Prior, same harness) **off-ladder quiz bloom** rescue — `repo.get_any_quiz_for_kp` (`tests/test_assess_any_bloom.py`).

A concrete worked example of a full corrected run is in
[`open-world-storyboard.md`](open-world-storyboard.md) (QEC · survey · lost-then-recover).

## Results — 10 scenarios × variants (all live, post-fix)
**10/10 reached `done`. 8 mastered, 2 conceded (give_up, correctly). Teaching + artifact in the
learner's language 10/10. ~$0.0182/session, $0.18 total.**

| # | scenario · lang | persona | outcome | branch exercised | teach/art lang | $ |
|--|--|--|--|--|--|--|
| 1 | diffusion · en | mastery | 4/4 mastered | advance | en/en ✓ | .020 |
| 2 | CRISPR · 中 | struggle | 4/4 mastered | **reteach → recover** | 中/中 ✓ | .020 |
| 3 | raft · en | give_up | 0/4 (all conceded) | reteach → **concede** | en/en ✓ | .018 |
| 4 | QEC · en | lost_then_recover | 5/5 mastered | **handle_lost → recover** | en/en ✓ | .015 |
| 5 | black-scholes · es | mastery | 4/4 mastered | advance | es/es ✓ | .021 |
| 6 | mRNA · en | struggle | 4/4 mastered | **reteach → recover** | en/en ✓ | .016 |
| 7 | attention · 中 | mastery | 5/5 mastered | advance | 中/中 ✓ | .017 |
| 8 | nudges · en | give_up | 0/4 (all conceded) | reteach → **concede** | en/en ✓ | .016 |
| 9 | rlhf · en | struggle | 4/4 mastered | **reteach → recover** | en/en ✓ | .020 |
| 10 | GNN · fr | lost_then_recover | 4/4 mastered | **handle_lost → recover** | fr/fr ✓ | .019 |

## Branch coverage — all four inner-loop branches fire correctly
- **advance** (mastery answers correctly → concept `done`): #1, #5, #7 ✓
- **reteach → recover** (wrong once → `reteach_kp` switches strategy → passes): #2, #6, #9 ✓
- **concede** (persistent wrong → `advance_kp` marks `conceded`, never false mastery): #3, #8 ✓
- **handle_lost → recover** ("I'm lost" → re-explain with a new strategy, no grade → recovers): #4, #10 ✓
- No infinite loops anywhere (the bloom-ceiling fix holds across all survey/functional goals).

## Actual content quality (frontier `gpt-4o` judge, 1–5, strict)
**Honest answer: NOT uniformly high quality.** Mechanically all 10 run; on *content*, **6/10 are good
(overall ≥ 4), 3 mediocre (3), 1 poor (2)** — mean **3.99** across 90 dimension-scores. The judge graded
the tutor's real outputs against the source evidence.

| # | scenario · persona · lang | src | teach | quiz | fb | re-lost | art | lang | grnd | **OVR** |
|--|--|--|--|--|--|--|--|--|--|--|
| 1 | diffusion · mastery · en | 5 | 4 | 5 | 4 | 5 | 4 | 5 | 5 | **4** |
| 2 | CRISPR · struggle · 中 | 5 | 5 | 4 | 4 | 5 | 5 | 5 | 5 | **5** |
| 3 | raft · give_up · en | 1 | 2 | 2 | 2 | 5 | 2 | 5 | 3 | **2** |
| 4 | QEC · lost · en | 4 | 3 | 3 | 3 | 4 | 3 | 5 | 4 | **3** |
| 5 | black-scholes · mastery · es | 5 | 4 | 4 | 4 | 5 | 4 | 5 | 5 | **4** |
| 6 | mRNA · struggle · en | 5 | 4 | 3 | 3 | 5 | 4 | 5 | 4 | **4** |
| 7 | attention · mastery · 中 | 3 | 3 | 4 | 4 | 5 | 3 | 5 | 4 | **3** |
| 8 | nudges · give_up · en | 5 | 4 | 3 | 2 | 5 | 4 | 5 | 5 | **4** |
| 9 | rlhf · struggle · en | 2 | 3 | 3 | 3 | 5 | 3 | 5 | 4 | **3** |
| 10 | GNN · lost · fr | 5 | 4 | 4 | 4 | 5 | 4 | 5 | 5 | **4** |
| | **mean** | 4.0 | 3.6 | 3.5 | 3.3 | 4.9 | 3.6 | **5.0** | 4.4 | **3.6** |

**Strong dimensions:** language fluency **5.0** (A8 holds across en/中/es/fr), lost-recovery re-explain
**4.9**, groundedness **4.4** (faithful to source, no hallucination).

**Weak dimensions:** feedback **3.3** (generic — "correctly identifies the purpose", doesn't explain *why*
or guide), quiz **3.5** (repetitive — single-keypoint concepts get near-identical comprehension questions),
teaching/artifact **3.6** (acceptable but shallow for mastery-depth goals).

**The biggest quality killer is DISCOVER picking a topically-adjacent-but-WRONG source** — the relevance
gate (OW-3.1) stops *gross* mismatches (films) but still passes *near-misses*:
- **#3 raft → a PBFT paper** (overall **2**) — "consensus" passed the gate, but PBFT ≠ Raft, so the whole session is off-goal;
- **#9 rlhf → a QLoRA/Guanaco paper** (source_relevance **2**) — fine-tuning, but not RLHF;
- **#7 transformer "数学原理/math" → a vision-transformer attention paper** (src **3**) — related, but no math depth.
(Note: give_up's low marks on #3 are the *wrong source*, not the persona — #8 give_up still scored overall 4.)

## Findings
- **A8 output-language: 10/10** — teaching *and* artifacts are produced in the learner's language across
  **English, 中文, Español, Français**. (Concept *names* follow the source language; the generated prose
  follows the learner — the intended behaviour.)
- **Honest concede:** give_up sessions mark every concept `conceded` (mastery 0/12) rather than claiming
  mastery — the learner model stays truthful.
- **V1 — prereq-detour not on the keypoint path:** `route_version == 1` for all 10 → `diagnose→replan`
  (prerequisite insertion) **never fires** for digested concepts; the keypoint path handles difficulty via
  reteach → concede only. The "learn the prerequisite first" detour is legacy-path-only. **Recorded as
  A12** (wire prereq-detour into the open-world keypoint path).
- **V2 — mid-session goal pivot not modelled:** `goal_elicit` runs once; an explicit goal change mid-session
  isn't supported (would need a re-elicit/branch). **Recorded as A13.**
- **Cost:** a full multi-concept tutoring session (discover→digest→teach⇄assess loop→artifact) is
  **~$0.018**; the full quality run incl. the frontier judge was **$0.269** for all 10.

## Quality-driven actions (recorded)
- **A14 (P1) — DISCOVER relevance PRECISION.** The gate stops gross off-topic but passes adjacent-but-wrong
  sources (raft→PBFT, rlhf→QLoRA, transformer-*math*→vision-attention). Add a goal-specificity check
  (named-algorithm / sub-topic match), not just topical adjacency. This is the dominant quality limiter.
- **A15 (P2) — quiz variety.** `assess_next` re-poses near-identical questions on single-keypoint concepts;
  vary stem/angle per Bloom rung, or require ≥N distinct keypoints.
- **A16 (P2) — feedback depth.** Grading feedback is generic; have `grade_kp` explain *why* and point to the
  next step (it has the evidence + rubric to do so).
- (carried) A11 digest cost, A12 prereq-detour on keypoint path, A13 mid-session goal pivot.
