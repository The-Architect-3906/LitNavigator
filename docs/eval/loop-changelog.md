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
