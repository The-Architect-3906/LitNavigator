# Improvement Backlog (ranked, adversarially reviewed)

Source: `research-report.md` (deep-research, 13-agent). Each item maps to a scorecard `metric`; `verdict` is the devil's-advocate review. **No item was dropped**; most are *revise* (kernel sound, metric-mapping or scope needs fixing — which independently confirms the near-ceiling-eval limitation).

| ID | Stage | Score | Effort | Risk | Metric | Verdict | Hypothesis | Status |
|---|---|:--:|:--:|:--:|---|:--:|---|---|
| R1 | learner-model | 9 | S | low | objective_quality | revise | Rename the keypoint mastery mechanism to 'BKT-lite heuristic' CONSISTENTLY across methods.md/storyboard.md/UI so no per-step table asserts plain 'BKT (Corbett & Anderson 1995)', matching the already-h… | ✅ applied (doc honesty; pyBKT follow-on skipped per verdict) |
| R3 | assess | 8.5 | S | low | reteach_recovery | revise | Deliver the spaced retrieval probes already enqueued: at session start / concept transitions, pop due review_queue items as low-stakes retrieval quizzes BEFORE new teaching, logging predicted-vs-actua… | pending (needs live eval / harder probe) |
| R4 | digest | 8 | S | low | objective_quality | revise | Reframe the edge-signal citation from 'RefD (Liang 2015)' to 'RefD-inspired corpus reference-distance + LLM judge-and-explain (cf. ACE, JEDM 2024)', add the ACM 2025 prereq survey as the framing ancho… | pending (needs live eval / harder probe) |
| R5 | assess | 7.5 | M | low | quiz_validity | revise | Upgrade flaw_gate from structural-only to an LLM-judge pass against an explicit item-writing-flaw checklist (cueing, implausible/heterogeneous distractors, all-of-the-above, negative stems, grammatica… | pending (needs live eval / harder probe) |
| R6 | grade | 7.5 | M | med | grading_acc | revise | Drive mastery (kp_bump) from the existing 0-5 partial-credit score instead of the binary correct flag, and add a component-extraction step (list key-idea components present/missing) before scoring. Li… | pending (needs live eval / harder probe) |
| R8 | discover | 7 | S | low | objective_quality | keep | Fix venue/framing for submission: RouteLLM = ICLR 2025 (not 'ACL 2025'); ReAct = ICLR 2023 (2022 preprint); soften 'specialised KT always beats LLMs' to 'comparable-or-better accuracy at 600-12000x lo… | ✅ applied (venue fixes; verdict=keep) |
| R2 | assess | 8.5 | S | low | quiz_validity | (applied pre-review) | overgenerate-AND-rank distractors | ✅ applied |
