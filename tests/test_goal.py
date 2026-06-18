import json
from litnav.goal import resolve_goal

_DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))
CONCEPTS = _DATA["concepts"]
OFF = _DATA["induction"]["off_skeleton"]


def test_maps_to_curated_concept_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("I want to understand ReAct", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "react"


def test_maps_to_off_skeleton_induction_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("I keep seeing multi-agent debate, where does it fit?", CONCEPTS, OFF)
    assert r["kind"] == "induce" and r["slug"] == "multi_agent_debate"


def test_unknown_goal_lists_available(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("teach me quantum chromodynamics", CONCEPTS, OFF)
    assert r["kind"] == "unknown" and any("ReAct" in n for n in r["available"])


def test_empty_goal_is_unknown(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert resolve_goal("   ", CONCEPTS, OFF)["kind"] == "unknown"


def test_hallucinated_llm_slug_falls_back_to_keyword(monkeypatch):
    from litnav import goal as goal_mod
    monkeypatch.setattr(goal_mod.llm_client, "complete_json",
                        lambda *a, **k: {"slug": "totally_made_up"})
    r = resolve_goal("tell me about reflection and self-correction", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "reflection"


def test_valid_llm_slug_is_used(monkeypatch):
    from litnav import goal as goal_mod
    monkeypatch.setattr(goal_mod.llm_client, "complete_json",
                        lambda *a, **k: {"slug": "agent_memory"})
    r = resolve_goal("how do agents remember things across steps", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "agent_memory"
