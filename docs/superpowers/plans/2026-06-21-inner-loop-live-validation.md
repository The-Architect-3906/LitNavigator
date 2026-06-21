# Inner-loop live validation Plan

> **For agentic workers:** controller-built harness (not subagent tasks). TDD-lite: validate the graph driver OFFLINE ($0) first, then run LIVE.

**Goal:** Prove the full LangGraph tutoring inner loop works end-to-end on **freshly-digested open-world graphs** (not curated fixtures), across all 10 scenarios + interaction variants, in the learner's language, with granular citations — the one path never validated live.

**What's already live-verified (stages, individually):** discover→digest→goal-elicit→one grade→artifact (the e2e harness). **What this adds:** the *compiled graph* run turn-by-turn — `goal_elicit → planner → orient → select_next → retrieve → teach_kp(×keypoints) → assess_next → grade_kp → {reteach_kp | advance_kp | concede} → select_next → … → done`.

## Driving mechanism
`build_graph(conn, ckpt, interrupt_after=["assess_next"])`; `make_initial_state(sid, topic, target_ids, goal_text=…)`; invoke; then loop: `get_state` → if `.next` empty, done; else read `current_quiz_item`, produce a learner answer, `update_state({"pending_answers":[ans],"user_answer":ans})`, `invoke(None)`. Cap turns (recursion_limit 80, MAX_TURNS guard).

## Learner personas (scripted on REAL data → deterministic branch coverage; correct = the quiz's real answer_key so grading is genuine)
| persona | answer policy | branch exercised |
|--|--|--|
| `mastery` | always the real answer_key | teach→assess→grade(correct)→advance→done |
| `struggle` | wrong once per keypoint, then answer_key | grade(wrong)→reteach_kp→recover→advance |
| `give_up` | always a plausible-wrong string | reteach exhausted → concede honestly |
| `lost_then_recover` | set `user_intent="lost"` once → then answer_key | assess_next→handle_lost→re-explain→recover |

## Scenario × persona matrix (all 10 base scenarios get the inner loop; personas spread to cover every branch)
1 diffusion=mastery · 2 CRISPR(中)=struggle · 3 raft=give_up · 4 QEC=lost_then_recover · 5 black-scholes(es)=mastery · 6 mRNA=struggle · 7 attention(中)=mastery · 8 nudges=give_up · 9 rlhf=struggle · 10 GNN(fr)=lost_then_recover.

## Variants (dedicated, beyond the base 10)
- **V1 prereq-detour / intent pivot** ("neural nets but learn linear algebra first"): digest a topic with a real prereq edge; fail the dependent concept; **observe whether `diagnose→replan` inserts the prereq**. Expected finding: the keypoint path routes via `reteach/advance`, NOT `diagnose→replan` (legacy-only) — DOCUMENT the gap.
- **V2 explicit goal pivot mid-session**: graph runs `goal_elicit` once; a mid-session goal change is not modeled → run as two sessions (goal A → goal B=prereq). DOCUMENT the supported mechanism.

## Assertions / logging per scenario (written to docs/e2e-logs/innerloop-*.md + summary)
- graph reached `done`; route progressed (≥1 concept advanced or conceded);
- ≥1 real `teach_kp` turn + ≥1 real `grade_kp` (metered); for `struggle`, a `reteach_kp` fired; for `give_up`, a `concede`; for `lost_*`, a `handle_lost`;
- teaching text + feedback are in the learner's language (A8);
- final artifact non-empty, cited, citations resolve, granular (>1 distinct citation where source sub-chunked — A9);
- per-scenario cost + was_live.

## Findings to expect (document, don't hide)
- replan/prereq-detour coverage on keypoint path (V1);
- mid-session goal pivot support (V2);
- any branch that doesn't fire; cost per full session (digest dominates).

## Steps
1. Build `litnav/evaluation/inner_loop_scenarios.py` (driver + personas + matrix + variants).
2. **OFFLINE smoke ($0):** digest a candidate fixture offline → run the driver with each persona on the deterministic graph → confirm the loop reaches `done` and branches fire. (Validates driver mechanics with no spend.)
3. **LIVE run:** all 10 + V1/V2; write per-scenario logs + summary; three-part report; update STATUS + eval doc.
