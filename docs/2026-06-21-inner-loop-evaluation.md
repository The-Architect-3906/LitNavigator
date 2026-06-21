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
  **~$0.018**; digest's frontier judges still dominate (A11).
