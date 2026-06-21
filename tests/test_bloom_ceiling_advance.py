"""Regression: assess_decider must respect the goal's Bloom CEILING.

Found by the inner-loop storyboard capture: a survey goal (ceiling=comprehension) kept trying to
upgrade Bloom past its ceiling -> assess_next capped it and re-posed the same question forever ->
the concept never advanced (infinite re-quiz loop). Below the ceiling it must still upgrade; at the
ceiling with a correct+mastered answer it must hand off to the advance check, not re-loop.
"""
from litnav.nodes.grade_kp import assess_decider


def _state(bloom, ceiling, mastery, correct_obs=3, last="correct"):
    return {
        "session_id": "s", "route": [], "route_version": 1, "bloom_ceiling": ceiling,
        "concept_progress": {
            "current_keypoint_id": "kp1", "current_bloom": bloom,
            "keypoint_state": {"kp1": {"mastery": mastery, "correct_obs": correct_obs,
                                       "last_result": last, "reteach_count": 0}},
        },
    }


def test_at_ceiling_mastered_advances_not_reloops():
    # survey: ceiling=comprehension; correct + mastered at the ceiling → advance (the bug: assess_next)
    assert assess_decider(_state("comprehension", "comprehension", 0.9)) == "advance_kp"


def test_below_ceiling_still_upgrades_bloom():
    # mastery: ceiling=application; correct at recall → keep climbing the ladder
    assert assess_decider(_state("recall", "application", 0.9)) == "assess_next"


def test_at_ceiling_not_yet_mastered_requizzes_no_premature_concede():
    # correct at the ceiling but mastery below threshold → keep quizzing (hold→assess_next), not concede
    assert assess_decider(_state("comprehension", "comprehension", 0.4, correct_obs=1)) == "assess_next"
