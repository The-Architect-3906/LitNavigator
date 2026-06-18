from litnav.nodes.select_next import select_next_node


def _state(strategy, route):
    return {"current_strategy": strategy, "current_cited_chunks": ["x"], "route": route}


def test_select_next_resets_strategy_for_a_new_concept():
    """Moving to a new concept must clear current_strategy, else a previous concept's
    reteach strategy (e.g. worked_example) leaks into the new concept's first teach,
    which should always start at 'direct'."""
    route = [{"concept_id": 1, "status": "conceded"},
             {"concept_id": 6, "status": "pending"}]
    out = select_next_node(_state("worked_example", route))
    assert out["current_concept_id"] == 6
    assert out["current_strategy"] is None, "strategy must reset for a fresh concept"


def test_select_next_end_when_no_pending():
    out = select_next_node(_state("analogy", [{"concept_id": 1, "status": "done"}]))
    assert out["current_concept_id"] is None
