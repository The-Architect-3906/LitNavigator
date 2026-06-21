from litnav.eval.mastery_probe import run_retention


def test_probes_raise_retention_for_a_forgetting_learner():
    on = run_retention(probes_on=True)
    off = run_retention(probes_on=False)
    assert 0.0 <= off <= on <= 1.0
    assert on - off > 0.0          # the spaced-retrieval mechanism raises retention
