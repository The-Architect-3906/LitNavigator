import sqlite3

from litnav.graph.router import tutor_router
from litnav.nodes.check import check_node
from litnav.nodes.concede import concede_node
from litnav.nodes.grade import grade_node
from litnav.nodes.reteach import reteach_node
from litnav.nodes.retrieve import retrieve_node
from litnav.nodes.teach import teach_node
from litnav.state import initial_concept_state
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_m2.json"
REACT = 1


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    repo.create_session(conn, "s", "agents")
    return conn


def _base_state():
    return {
        "session_id": "s",
        "current_concept_id": REACT,
        "learner_state": {REACT: initial_concept_state()},
        "concept_dag": {REACT: []},          # react is a root
        "mastery_threshold": 0.75,
        "reteach_count": {},
        "route": [{"step_id": "r1", "concept_id": REACT, "status": "pending"}],
        "route_version": 1,
        "current_evidence": [],
        "current_strategy": "direct",
        "current_cited_chunks": [],
        "used_quiz_ids": {},
        "pending_answers": [],
        "history": [],
    }


def _apply(state, updates):
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def _drive(state, conn, answer):
    state = _apply(state, retrieve_node(state, conn))
    state = _apply(state, teach_node(state, conn))
    state = _apply(state, check_node(state, conn))
    state = {**state, "pending_answers": [answer]}
    return _apply(state, grade_node(state, conn))


def test_teach_cites_chunk():
    conn = _conn()
    s = _apply(_base_state(), retrieve_node(_base_state(), conn))
    out = teach_node(s, conn)
    assert out["current_cited_chunks"], "teach must cite at least one chunk"
    assert out["current_cited_chunks"][0].startswith("c_react")


def test_grade_detects_react_is_cot_misconception():
    conn = _conn()
    s = _drive(_base_state(), conn, "it just uses chain of thought reasoning")
    assert s["quiz_result"]["detected_misconception"] == "react_is_just_cot"
    assert "react_is_just_cot" in s["learner_state"][REACT]["held_misconceptions"]
    assert s["quiz_result"]["score"] == 0.0


def test_correct_answer_clears_misconception_and_raises_mastery():
    conn = _conn()
    s = _drive(_base_state(), conn, "the agent takes actions and observations")
    assert s["quiz_result"]["score"] == 1.0
    assert s["learner_state"][REACT]["held_misconceptions"] == []
    assert s["learner_state"][REACT]["mastery"] >= 0.75


def test_confidence_below_mastery_on_first_observation():
    conn = _conn()
    s = _drive(_base_state(), conn, "the agent takes actions and observations")
    cs = s["learner_state"][REACT]
    assert cs["n_observations"] == 1
    assert cs["confidence"] < cs["mastery"]  # one observation -> low confidence


def test_reteach_switches_strategy():
    conn = _conn()
    s = _drive(_base_state(), conn, "chain of thought")        # wrong -> holds misconception
    assert tutor_router(s) == "reteach"
    out = reteach_node(s, conn)
    assert out["current_strategy"] == "analogy"                # first unused after 'direct'
    assert out["reteach_count"][REACT] == 1


def test_router_concedes_when_reteach_exhausted():
    conn = _conn()
    s = _base_state()
    s["learner_state"][REACT].update(mastery=0.34, held_misconceptions=["react_is_just_cot"])
    s["reteach_count"] = {REACT: 2}
    assert tutor_router(s) == "concede"


def test_concede_marks_step_and_lowers_confidence():
    conn = _conn()
    s = _base_state()
    s["learner_state"][REACT].update(mastery=0.34, confidence=0.64,
                                     tried_strategies=["direct", "analogy", "worked_example"])
    out = concede_node(s, conn)
    assert out["learner_state"][REACT]["confidence"] <= 0.3
    assert any(step["status"] == "conceded" for step in out["route"])


def test_parallel_quiz_forms_differ_pre_post():
    conn = _conn()
    s = _base_state()
    out1 = check_node(s, conn)
    s = {**s, **out1}
    out2 = check_node(s, conn)
    assert out1["current_quiz_item"]["id"] != out2["current_quiz_item"]["id"]


def test_grade_rejects_unknown_llm_misconception_id(monkeypatch):
    """A live LLM returning a bogus id must not pollute state; fall back to deterministic."""
    from litnav.nodes import grade as grade_mod
    monkeypatch.setattr(grade_mod.llm_client, "complete_json",
                        lambda *a, **k: {"misconception_id": "totally_made_up"})
    conn = _conn()
    s = _drive(_base_state(), conn, "it just uses chain of thought reasoning")
    assert s["quiz_result"]["detected_misconception"] == "react_is_just_cot"
    assert "totally_made_up" not in s["learner_state"][REACT]["held_misconceptions"]


def test_grade_accepts_valid_llm_misconception_id(monkeypatch):
    """When the deterministic check misses but the LLM returns a valid candidate id, accept it."""
    from litnav.nodes import grade as grade_mod
    monkeypatch.setattr(grade_mod.llm_client, "complete_json",
                        lambda *a, **k: {"misconception_id": "react_is_just_cot"})
    conn = _conn()
    s = _drive(_base_state(), conn, "I really have no idea honestly")
    assert s["quiz_result"]["detected_misconception"] == "react_is_just_cot"
