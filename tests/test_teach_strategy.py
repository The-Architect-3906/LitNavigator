"""Tests for teach strategy policy (spec §6.3) + metacognitive anti-over-help reteach."""
from litnav.assess import strategy


def test_choose_strategy_policy():
    assert strategy.choose_strategy("mastery", "novice", 0.2) in {"worked_example", "direct"}
    assert strategy.choose_strategy("mastery", "novice", 0.5) == "analogy"      # mid mastery -> analogy
    assert strategy.choose_strategy("survey", "novice", 0.2) == "overview"      # survey goal -> concise overview
    assert strategy.choose_strategy("mastery", "expert", 0.2) == "concise"      # expert -> concise
    # deterministic: same inputs -> same output
    assert strategy.choose_strategy("mastery", "novice", 0.2) == strategy.choose_strategy("mastery", "novice", 0.2)


def test_reteach_is_metacognitive_and_anti_over_help(monkeypatch):
    # the reteach prompt must (a) ask a metacognitive question and (b) NOT reveal the answer key verbatim
    import sqlite3
    from litnav.storage.schema import init_db
    from litnav.storage import repo
    from litnav.nodes import reteach_kp
    from litnav.llm import router

    captured = {}

    def fake(prompt, *, tier, stage, fallback, **k):
        captured["prompt"] = prompt
        return "re-explanation"

    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setattr(router, "complete_text", fake)
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="t")
    # seed a concept and keypoint so the node can look them up
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'test-concept', 'TestConcept')")
    c.execute(
        "INSERT INTO keypoints (id, concept_id, name, objective, evidence_chunk_id, sort_order) "
        "VALUES ('kp1', 1, 'KP Name', 'Learn X', NULL, 0)"
    )
    c.commit()

    # minimal state for reteach_kp — adapted to what the node actually reads
    state = {
        "session_id": "s",
        "route_version": 1,
        "concept_progress": {
            "concept_id": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {"kp1": {"mastery": 0.3, "reteach_count": 0, "strategies_used": []}},
            "misconceptions": {},
        },
        "current_quiz_item": {"answer_key": "SECRETANSWER", "question": "q?"},
        "current_cited_chunks": [],
        "history": [],
        "goal_type": "mastery",
    }
    reteach_kp.reteach_kp_node(state, c)
    p = captured.get("prompt", "")
    assert "SECRETANSWER" not in p                       # anti-over-help: answer not revealed in the prompt
    assert any(w in p.lower() for w in ("unclear", "which part", "confus", "stuck", "what about"))  # metacognitive
