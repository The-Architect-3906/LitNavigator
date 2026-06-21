from litnav.eval.scorecard import Scorecard, weighted_headline, is_improvement


def _sc(**kw):
    base = dict(
        commit="c", ts=0.0,
        e2e={"mastered_rate": 0.5, "avg_turns": 10, "usd": 0.01},
        golden={"grading_acc": 0.8, "prereq_survival": 0.5, "objective_quality": 0.8,
                "quiz_validity": 0.9, "discover_relevance": 0.7},
        learning_gain={"avg_mastery_delta": 0.3},
        offline_suite={"passed": 275, "total": 275}, notes="",
    )
    base.update(kw)
    return Scorecard(**base)


def test_headline_rises_with_learning_metrics():
    lo = _sc()
    hi = _sc(e2e={"mastered_rate": 0.7, "avg_turns": 10, "usd": 0.01})
    assert weighted_headline(hi) > weighted_headline(lo)


def test_improvement_true_when_primary_up_guardrails_ok():
    base = _sc()
    cand = _sc(golden={**base.golden, "grading_acc": 0.9})
    ok, _ = is_improvement(base, cand)
    assert ok


def test_regression_in_offline_suite_blocks():
    base = _sc()
    cand = _sc(e2e={"mastered_rate": 0.9, "avg_turns": 8, "usd": 0.01},
               offline_suite={"passed": 274, "total": 275})
    ok, why = is_improvement(base, cand)
    assert not ok and "offline" in why.lower()


def test_cost_blowout_blocks():
    base = _sc()
    cand = _sc(e2e={"mastered_rate": 0.9, "avg_turns": 8, "usd": 0.05})  # +400%
    ok, why = is_improvement(base, cand)
    assert not ok and "cost" in why.lower()
