"""Tests for A8: language threading into teach_kp, grade_kp, reteach_kp nodes."""
import sqlite3
import pytest
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.llm import router


# ── Shared helpers ───────────────────────────────────────────────────────────

def _make_state(language: str | None = "Chinese") -> dict:
    """Build a minimal NavState-shaped dict matching what teach/grade/reteach nodes expect."""
    return {
        "session_id": "s",
        "target_language": language,
        "goal_type": "mastery",
        "intent": None,
        "route_version": 1,
        "concept_progress": {
            "concept_id": 1,
            "phase": "teaching",
            "keypoints": ["kp1"],
            "taught_idx": 0,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {
                "kp1": {
                    "keypoint_id": "kp1",
                    "mastery": 0.3,
                    "correct_obs": 0,
                    "last_result": None,
                    "reteach_count": 0,
                    "strategies_used": [],
                }
            },
            "misconceptions": {},
        },
        "current_quiz_item": {
            "id": 1,
            "question": "What is CRISPR?",
            "answer_key": "a gene-editing tool",
            "rubric": "mention gene editing",
            "expected_keypoints": "gene editing",
            "evidence_chunk_id": None,
            "targets_misconception": None,
        },
        "pending_answers": ["it edits genes"],
        "user_answer": "it edits genes",
        "current_cited_chunks": [],
        "learner_state": {},
        "history": [],
    }


def _seed_db(conn):
    """Seed minimum DB rows for teach/grade/reteach."""
    conn.execute("INSERT OR IGNORE INTO papers(id, title) VALUES (1, 'Test Paper')")
    conn.execute(
        "INSERT OR IGNORE INTO concepts(id, slug, name) "
        "VALUES (1,'crispr','CRISPR')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO paper_chunks(id, paper_id, chunk_index, text, concept_id) "
        "VALUES ('chunk-1', 1, 0, 'CRISPR-Cas9 enables precise genomic editing.', 1)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO keypoints(id, concept_id, name, objective, evidence_chunk_id, sort_order) "
        "VALUES ('kp1', 1, 'CRISPR mechanism', 'Understand how CRISPR edits genes', 'chunk-1', 0)"
    )
    conn.commit()


# ── teach_kp: prompt contains language ──────────────────────────────────────

def test_teach_kp_prompt_contains_language(monkeypatch):
    """teach_kp_node should include 'Chinese' in its LLM prompt when target_language='Chinese'."""
    from litnav.nodes import teach_kp

    captured = {}

    def fake_text(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_text", fake_text)

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")
    _seed_db(c)

    state = _make_state(language="Chinese")
    teach_kp.teach_kp_node(state, c)

    assert "Chinese" in captured.get("prompt", ""), (
        "Expected 'Chinese' in teach_kp LLM prompt, got: " + repr(captured.get("prompt"))
    )


def test_teach_kp_defaults_to_english_when_no_language(monkeypatch):
    """teach_kp_node should use 'English' when target_language is absent."""
    from litnav.nodes import teach_kp

    captured = {}

    def fake_text(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_text", fake_text)

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")
    _seed_db(c)

    state = _make_state(language=None)   # no language set
    teach_kp.teach_kp_node(state, c)

    assert "English" in captured.get("prompt", ""), (
        "Expected 'English' fallback in teach_kp LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── grade_kp: prompt contains language ──────────────────────────────────────

def test_grade_kp_prompt_contains_language(monkeypatch):
    """grade_kp_node should include 'Chinese' in its grading LLM prompt when target_language='Chinese'."""
    from litnav.nodes import grade_kp

    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback   # return fallback so function continues

    monkeypatch.setattr(router, "complete_json", fake_json)

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")
    _seed_db(c)

    state = _make_state(language="Chinese")
    # grade_kp.grade_kp_node calls repo functions; patch the ones it calls to avoid DB deps
    grade_kp.grade_kp_node(state, c)

    assert "Chinese" in captured.get("prompt", ""), (
        "Expected 'Chinese' in grade_kp LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── reteach_kp: prompt contains language ────────────────────────────────────

def test_reteach_kp_prompt_contains_language(monkeypatch):
    """reteach_kp_node should include 'Chinese' in its LLM prompt when target_language='Chinese'."""
    from litnav.nodes import reteach_kp

    captured = {}

    def fake_text(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_text", fake_text)

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")
    _seed_db(c)

    state = _make_state(language="Chinese")
    state["concept_progress"]["phase"] = "assessing"
    state["concept_progress"]["taught_idx"] = 1
    reteach_kp.reteach_kp_node(state, c)

    assert "Chinese" in captured.get("prompt", ""), (
        "Expected 'Chinese' in reteach_kp LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── goal_elicit_node: sets target_language ──────────────────────────────────

def test_goal_elicit_sets_target_language_offline(monkeypatch):
    """goal_elicit_node should set target_language from the goal text (offline heuristic)."""
    from litnav.nodes import goal_elicit

    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")

    state = {
        "session_id": "s",
        "topic": "CRISPR",
        "goal_text": "给我一个关于 CRISPR 的概览",  # Chinese
        "target_concept_ids": [],
        "history": [],
    }
    result = goal_elicit.goal_elicit_node(state, c)

    assert result.get("target_language") == "Chinese", (
        "Expected target_language='Chinese' for Chinese goal text, got: "
        + repr(result.get("target_language"))
    )


def test_goal_elicit_sets_english_for_english_goal(monkeypatch):
    """goal_elicit_node should set target_language='English' for an English goal."""
    from litnav.nodes import goal_elicit

    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="CRISPR")

    state = {
        "session_id": "s",
        "topic": "CRISPR",
        "goal_text": "I want to master CRISPR gene editing",
        "target_concept_ids": [],
        "history": [],
    }
    result = goal_elicit.goal_elicit_node(state, c)

    assert result.get("target_language") == "English", (
        "Expected target_language='English', got: " + repr(result.get("target_language"))
    )
