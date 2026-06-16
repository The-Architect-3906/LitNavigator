from litnav.graph.router import tutor_router


def test_router_advances_when_mastered():
    state = {
        "current_concept_id": 1,
        "mastery_threshold": 0.8,
        "learner_state": {1: {"mastery": 0.82, "held_misconceptions": []}},
        "concept_dag": {1: []},
        "reteach_count": {},
    }
    assert tutor_router(state) == "advance"


def test_router_diagnoses_when_prereq_missing():
    state = {
        "current_concept_id": 4,
        "mastery_threshold": 0.8,
        "learner_state": {
            1: {"mastery": 0.4, "held_misconceptions": []},
            4: {"mastery": 0.4, "held_misconceptions": []},
        },
        "concept_dag": {4: [1]},
        "reteach_count": {},
    }
    assert tutor_router(state) == "diagnose"


def test_router_reteaches_when_misconception_and_prereqs_ok():
    state = {
        "current_concept_id": 1,
        "mastery_threshold": 0.8,
        "learner_state": {1: {"mastery": 0.5, "held_misconceptions": ["dr_is_keyword_match"]}},
        "concept_dag": {1: []},
        "reteach_count": {1: 0},
    }
    assert tutor_router(state) == "reteach"


def test_router_concedes_when_reteach_exhausted():
    state = {
        "current_concept_id": 1,
        "mastery_threshold": 0.8,
        "learner_state": {1: {"mastery": 0.5, "held_misconceptions": ["dr_is_keyword_match"]}},
        "concept_dag": {1: []},
        "reteach_count": {1: 2},
    }
    assert tutor_router(state) == "concede"
