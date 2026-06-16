from litnav.state import bkt_update, confidence_update, initial_concept_state


def test_bkt_correct_taught_reaches_money_shot_range():
    updated = bkt_update(0.40, correct=True, taught=True)
    assert 0.82 <= updated <= 0.83


def test_confidence_increases_with_observations():
    assert confidence_update(1) == 0.4
    assert confidence_update(2) > confidence_update(1)
    assert confidence_update(5) > confidence_update(3)


def test_initial_concept_state_separates_mastery_and_confidence():
    state = initial_concept_state()
    assert state["mastery"] == 0.4
    assert state["confidence"] == 0.0
    assert state["n_observations"] == 0
