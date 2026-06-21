"""Eval scorecard + keep/revert decision for the research-improvement loop.

A Scorecard is a comparable snapshot of LitNavigator quality at one commit: the live e2e subset,
the per-stage golden metrics, the learning-gain, and the offline-suite count. `is_improvement`
encodes the loop's keep/revert rule: primary learning metrics must rise while guardrails
(offline suite, per-stage golden, cost) must not regress beyond tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

# learning metrics that must RISE; guardrails that must NOT regress beyond tolerance.
_HEADLINE_WEIGHTS = {"mastered_rate": 0.4, "avg_mastery_delta": 0.35, "grading_acc": 0.25}
DEFAULT_TOL = {"golden_drop": 0.02, "cost_mult": 1.20}  # golden may dip <=2%; cost may rise <=20%


@dataclass
class Scorecard:
    commit: str
    ts: float
    e2e: dict            # {mastered_rate, avg_turns, usd}
    golden: dict         # {grading_acc, prereq_survival, objective_quality, quiz_validity, discover_relevance}
    learning_gain: dict  # {avg_mastery_delta}
    offline_suite: dict  # {passed, total}
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def weighted_headline(sc: Scorecard) -> float:
    vals = {
        "mastered_rate": sc.e2e.get("mastered_rate", 0.0),
        "avg_mastery_delta": sc.learning_gain.get("avg_mastery_delta", 0.0),
        "grading_acc": sc.golden.get("grading_acc", 0.0),
    }
    return round(sum(_HEADLINE_WEIGHTS[k] * vals[k] for k in _HEADLINE_WEIGHTS), 4)


def is_improvement(base: Scorecard, cand: Scorecard, *, tol: dict = DEFAULT_TOL) -> tuple[bool, str]:
    """Keep the candidate only if learning rises AND no guardrail regresses beyond tolerance."""
    # Guardrail 1: offline suite must not regress.
    if cand.offline_suite.get("passed", 0) < base.offline_suite.get("passed", 0):
        return False, f"offline suite regressed ({cand.offline_suite} < {base.offline_suite})"
    # Guardrail 2: no per-stage golden metric drops more than tol.
    for k, bv in base.golden.items():
        if cand.golden.get(k, 0.0) < bv - tol["golden_drop"]:
            return False, f"golden '{k}' regressed {bv:.3f}->{cand.golden.get(k, 0.0):.3f}"
    # Guardrail 3: cost must not balloon.
    b_usd, c_usd = base.e2e.get("usd", 0.0), cand.e2e.get("usd", 0.0)
    if b_usd > 0 and c_usd > b_usd * tol["cost_mult"]:
        return False, f"cost +{(c_usd / b_usd - 1) * 100:.0f}% (> {int((tol['cost_mult'] - 1) * 100)}%)"
    # Primary: weighted headline must rise.
    if weighted_headline(cand) <= weighted_headline(base):
        return False, "no headline gain"
    return True, f"headline {weighted_headline(base):.4f}->{weighted_headline(cand):.4f}"
