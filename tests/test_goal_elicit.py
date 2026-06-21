import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo, openworld_repo
from litnav.nodes import goal_elicit


def _state(goal):
    return {"session_id": "s", "topic": goal, "goal_text": goal, "history": []}


def test_offline_goal_type_heuristic(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    assert goal_elicit.classify_goal("I want to deeply master attention mechanisms", conn=c, session_id="s") == "mastery"
    assert goal_elicit.classify_goal("I need to be able to build a RAG pipeline", conn=c, session_id="s") == "functional"
    assert goal_elicit.classify_goal("give me a quick overview of LLM agents", conn=c, session_id="s") == "survey"


def test_node_persists_goal_and_sets_ceiling(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    out = goal_elicit.goal_elicit_node(_state("give me a quick overview of agents"), c)
    assert out["goal_type"] == "survey"
    assert out["bloom_ceiling"] == "comprehension"        # survey caps low on the ladder
    g = openworld_repo.get_goal(c, "s")
    assert g and g["goal_type"] == "survey"


def test_node_idempotent_if_goal_set(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    openworld_repo.set_goal(c, "s", "x", "mastery", [])
    out = goal_elicit.goal_elicit_node({**_state("anything"), "goal_type": "mastery"}, c)
    assert out["goal_type"] == "mastery"                  # respects already-set goal
