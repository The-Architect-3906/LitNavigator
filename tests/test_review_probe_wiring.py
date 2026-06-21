import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.graph.builder import _route_after_select_with_probe


def _seed():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "t")
    repo.create_concept(c, 1, "react", "ReAct")
    repo.create_keypoint(c, "kp1", 1, "k", "o", bloom_level="recall")
    repo.create_quiz_item(c, 1, "q", "a", keypoint_id="kp1", bloom_level="recall")
    return c


def test_route_to_review_probe_when_due_else_retrieve():
    c = _seed()
    state = {"current_concept_id": 2, "route": [{"concept_id": 1, "status": "done"}],
             "concept_last_seen": {1: 0}, "step": 3}
    assert _route_after_select_with_probe(state, c) == "review_probe"   # concept 1 due (3-0>=2)
    state["concept_last_seen"] = {1: 3}                                  # just seen → not due
    assert _route_after_select_with_probe(state, c) == "retrieve"


def test_route_end_when_no_concept_left():
    c = _seed()
    assert _route_after_select_with_probe({"current_concept_id": None}, c) == "__end__"


def test_graph_builds_with_probe_nodes():
    from litnav.graph.builder import build_graph
    c = _seed()
    ck = sqlite3.connect(":memory:")
    app = build_graph(c, ck)            # compiles with review_probe/grade_probe wired
    assert app is not None
