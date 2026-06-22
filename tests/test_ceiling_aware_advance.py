"""RC#1: a survey/functional goal must be completable.

A survey goal caps Bloom at comprehension, so the mastery climb peaks at 0.685 (recall .25 +
comprehension .40 from the 0.30 floor) — below the fixed advance gate of 0.75. So a survey learner
who answered EVERYTHING correctly could never advance, and the route stalled at concept 1 (live-test
B1, scenarios #4 QEC / #10 GNN). The advance target must be relative to the goal's Bloom ceiling.
"""
from litnav.state import mastery_target_for, KP_MASTERY_THRESHOLD
from litnav.nodes.route_decider import route_decider_node


def _state(masteries, correct_obs, ceiling):
    ks = {f"kp{i}": {"mastery": m, "correct_obs": correct_obs} for i, m in enumerate(masteries)}
    return {"concept_progress": {"keypoint_state": ks}, "bloom_ceiling": ceiling}


def test_mastery_target_scales_with_ceiling():
    # application ceiling keeps the historical 0.75 bar; lower ceilings get reachable bars.
    assert mastery_target_for("application") == KP_MASTERY_THRESHOLD
    assert mastery_target_for("comprehension") < KP_MASTERY_THRESHOLD
    assert mastery_target_for("recall") < mastery_target_for("comprehension")


def test_survey_learner_can_advance_at_comprehension_peak():
    # survey peak (0.685) with >=2 correct observations must ADVANCE, not hold.
    assert route_decider_node(_state([0.685], correct_obs=2, ceiling="comprehension")) == "advance"


def test_survey_learner_holds_after_only_recall():
    # one rung (0.475) is NOT enough even for a survey goal — must climb to the ceiling.
    assert route_decider_node(_state([0.475], correct_obs=1, ceiling="comprehension")) == "hold"


def test_mastery_goal_advance_unchanged():
    # application-ceiling behavior is exactly as before: needs 0.75 + >=2 obs.
    assert route_decider_node(_state([0.858], correct_obs=3, ceiling="application")) == "advance"
    assert route_decider_node(_state([0.685], correct_obs=2, ceiling="application")) == "hold"
