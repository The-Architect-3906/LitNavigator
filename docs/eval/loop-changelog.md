# Eval-gated loop — changelog

Baseline (offline): `headline=0.7063` — mastered_rate 1.0, avg_mastery_delta 0.518, reteach_recovery 1.0,
objective_quality 1.0, quiz_validity 1.0, grading_acc 0.5*, prereq_survival 0.5*  (*offline floor — these
only move under a live provider). Offline suite: 333→337 green.

## Important limitation found at loop start
The **offline eval is near-ceiling**: the probe metrics (mastered_rate, avg_mastery_delta, reteach_recovery)
and the structural golden (objective_quality, quiz_validity) are already maxed by the scripted learner +
fixtures, and grading_acc/prereq_survival sit at their offline floor (0.5). So the autonomous
keep-on-headline-gain rule **cannot discriminate most backlog items offline** — the genuinely measurable
gains live in the **live** grading/prereq path (R5, R6) or need a **harder probe** (a learner that
under-masters, so teaching/reteach changes have headroom). This is itself a finding: a near-ceiling eval
can't drive a loop. Next batch should (a) run live grading/prereq eval, and/or (b) add a stricter probe
profile, before the autonomous keep/revert loop is meaningful.

## Iterations

### R2 — overgenerate-AND-rank distractors  · stage=assess · kept (by inspection)
- **Change:** `litnav/assess/quizgen.py` `make_distractors` now ranks deduped candidates by
  misconception-plausibility (cheap LLM) and keeps the top *n*, instead of returning the first *n* —
  closing a literal docstring-vs-code gap the audit verified. New `_rank_distractors` helper.
- **Eval:** offline headline unchanged (0.7063 → 0.7063) — the ranker returns input order offline, so the
  effect is **live-only** and the structural quiz_validity golden can't see it. Kept on: closes a verified
  gap + **zero regression (337 green)** + correct by inspection. NOT an eval-gated keep — flagged honestly.
- **Citation:** Scarlatos et al., NAACL 2024 BEA (overgenerate-and-rank).

### R1 + R8 — claims/honesty fixes (docs) · stage=learner-model/discover · applied
- **R1 (BKT overstatement):** methods ④d and storyboard ⑥ now say **"BKT-lite mastery heuristic
  (cf. Corbett & Anderson 1995)"** instead of plain "BKT — Corbett & Anderson 1995", matching the
  honest spec §11/§12 and the verified code (`kp_bump` + linear confidence, not a fitted BKT). The
  cost line's "BKT/Rasch routing" → "mastery/difficulty updates are rule-based".
- **R8 (venue/claim errors):** RouteLLM **ACL 2025 → ICLR 2025**; ReAct **→ ICLR 2023** (arXiv:2210.03629);
  specialised-KT framing softened to "comparable at far lower cost" (not "always beats").
- **Eval:** docs-only, not eval-gated; serves Responsible-AI / Presentation. Not destructive to code.
- *Deferred (need live eval or larger work):* R4 (RefD/GraphRAG reframe — editorial, recommend Architect
  review), R3 (deliver spaced-retrieval probes), R5 (LLM flaw-gate), R6 (partial-credit grading) — all
  need the live grading/prereq eval + a harder probe to be keep/revert-gated meaningfully.

## Live eval-gated batch (R6/R5/R3) — empirical result
Ran the loop **live** (LITNAV_LLM_PROVIDER=openai) with a new harder probe profile
(`partial_then_full`) + a live-eval runner (`litnav/eval/probe_live.py`).

**Live baseline:** `headline=0.8313` — grading_acc **1.0**, prereq_survival **0.833**, objective/quiz 1.0,
mastered_rate 1.0, avg_mastery_delta 0.518.

**Finding — most targets are at ceiling, so no autonomous keep/revert gain is available:**
- **R6 (partial-credit grading):** `grading_acc` is already **1.0** (the GEPA key-idea grader nails all
  16 paraphrase/wrong cases) and the probe masters even *partial* answers (grader is lenient) — so R6
  has **no measurable headroom** here. Confirms the adversarial `revise` verdict and the exec-summary
  warning that items are tagged to metrics they can't causally move. **Not applied** (no eval gain).
- **R5 (LLM flaw-gate):** would move real quiz quality, but the structural `quiz_validity` golden is at
  1.0 and can't see it → not eval-gateable without a quality-graded golden. **Deferred.**
- **R3 (spaced retrieval):** probe `reteach_recovery` already 1.0 → no headroom. **Deferred.**

**The one genuine weak spot:** `prereq_survival = 0.833`. Diagnosed 2/12 failures: a **directionality
error** (judge accepts `RL → MDP`, the reversed dependency) and one debatable pair (`ReAct → multi-agent`).
This is a REAL product lever — but the golden currently calls a proxy judge (`run._live_judge`), not the
product's `digest/verify` judge. The honest next iteration: **wire the golden to the product prereq judge,
add an explicit directionality check to that judge's prompt, then keep/revert on `prereq_survival`.**

### Harness-correctness fix — wire prereq_survival to the PRODUCT judge · KEPT
- `run.py`: the prereq golden now calls **`digest.verify._judge`** (the real product judge, with
  descriptions + the strict "necessary, not merely helpful" rule) instead of a weak proxy prompt.
- **`prereq_survival` 0.833 (proxy) → 0.917 (product), live.** The proxy's directionality error
  (`RL → MDP` accepted) is **correctly rejected by the product judge** — i.e. the product was already
  strong; the earlier 0.833 was a measurement artifact. 337 tests green.
- The one remaining miss (`ReAct → multi-agent`) is a **debatable** pair; by the product's strict
  standard `False` is defensible, so the golden label was left as-is (NOT tuned to 1.0).

## Loop conclusion
Final live scorecard: `headline=0.8313` — grading_acc **1.0**, prereq_survival **0.917**,
objective/quiz **1.0**, mastered_rate **1.0**, avg_mastery_delta 0.518. With the eval now measuring the
**product** honestly, the system is at/near ceiling on every axis the harness can see. **No further
autonomous keep/revert gains are available** without either (a) quality-graded goldens (distractor/answer
quality beyond structural+binary) or (b) building the deferred product features (R3 spaced-retrieval
delivery, R5 LLM flaw-gate) whose benefit a structural eval cannot detect. The honest loop result is:
the measurable surfaces are strong; remaining work is feature-building, not parameter-tuning.
