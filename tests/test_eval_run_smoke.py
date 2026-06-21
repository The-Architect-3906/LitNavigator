from litnav.eval.run import build_scorecard
from litnav.eval.scorecard import weighted_headline


def test_build_scorecard_offline_is_valid():
    sc = build_scorecard(run_suite=False, commit="test")
    # all four golden metrics populated
    assert set(sc.golden) == {"grading_acc", "prereq_survival", "objective_quality", "quiz_validity"}
    # the probe ran (learning signal present and nonzero)
    assert sc.learning_gain["avg_mastery_delta"] > 0.0
    assert sc.e2e["mastered_rate"] >= 0.0
    # offline structural golden should be high (fixtures are classifier-correct)
    assert sc.golden["objective_quality"] >= 0.85
    assert sc.golden["quiz_validity"] >= 0.85
    # headline is a finite weighted number
    assert weighted_headline(sc) > 0.0
