from litnav.assess.retrieval import is_due, predicted_recall, reinforce


def test_is_due_needs_k_turns_and_a_prior_sighting():
    assert is_due(None, 5, k=2) is False          # never seen → not due
    assert is_due(3, 5, k=2) is True              # 2 turns ago → due
    assert is_due(4, 5, k=2) is False             # only 1 turn ago → not yet


def test_predicted_recall_is_clamped_mastery():
    assert predicted_recall(0.7) == 0.7
    assert predicted_recall(1.5) == 1.0
    assert predicted_recall(-0.2) == 0.0


def test_reinforce_is_low_stakes():
    assert 0.6 < reinforce(0.6, True) < 1.0       # gentle bump
    assert reinforce(0.6, False) == 0.5           # -0.10 nudge
    assert reinforce(0.05, False) == 0.0          # clamped at 0
