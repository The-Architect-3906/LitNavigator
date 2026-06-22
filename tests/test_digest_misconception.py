"""TDD test for A4/B6: DIGEST must seed ≥1 misconception per concept so
_detect_misconception fires on live/digested concepts.

Phase 1 (failing): verify the gap — no misconceptions after digest.
Phase 2 (passing): verify the fix — ≥1 misconception per concept + detection works.
"""
import re
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.nodes.grade import _detect_misconception


CANDIDATE = {
    "concepts": [
        {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
    ],
    "keypoints": [
        {"kp_id": "kp_tool_1", "concept_slug": "tool_use", "name": "What a tool call is",
         "objective": "define tool calls", "evidence_chunk_id": "c0", "bloom_level": "recall"},
    ],
    "prereq_edges": [
        {"prereq_slug": "tool_use", "target_slug": "reason_act",
         "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False},
    ],
    "similarity_edges": [],
    "quiz_seeds": [
        {"concept_slug": "tool_use", "question": "What is a tool call?", "answer_key": "...",
         "keypoint_id": "kp_tool_1", "bloom_level": "recall"},
    ],
    "judge_labels": {"tool_use->reason_act": True},
    # Offline fallback misconceptions — one per concept, with detect_hint for keyword matching.
    "misconceptions": [
        {
            "concept_slug": "tool_use",
            "wrong_model": "A tool call is just a function call in the code.",
            "correct_model": "A tool call is an LLM-directed invocation: the model emits a "
                             "structured request that the runtime executes and feeds back.",
            "detect_hint": "function|just a call|ordinary call",
            "reteach_strategy": "analogy",
        },
        {
            "concept_slug": "reason_act",
            "wrong_model": "Reasoning and acting are separate sequential phases.",
            "correct_model": "ReAct interleaves reasoning traces and actions so the agent "
                             "can ground its decisions in real-world observations.",
            "detect_hint": "separate|sequential|one after",
            "reteach_strategy": "analogy",
        },
    ],
}


def _input():
    return DigestInput(
        "llm-agents",
        [SourceDoc("arxiv", "2302.04761", "Toolformer", None, ["c0 text", "c1 text"])],
        target_slugs=[],
    )


def _conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    return c


def test_digest_seeds_misconception_per_concept(monkeypatch):
    """After digest(), every digested concept must have ≥1 misconception in the bank."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    pipeline.digest(_input(), conn=conn, candidate=CANDIDATE, session_id="s")

    concept_rows = conn.execute(
        "SELECT id, slug FROM concepts WHERE source='digested'"
    ).fetchall()
    assert concept_rows, "No digested concepts found — digest itself is broken"

    for cid, slug in concept_rows:
        misconceptions = repo.get_misconceptions_for_concept(conn, cid)
        assert misconceptions, (
            f"Concept '{slug}' (id={cid}) has 0 misconceptions after digest — "
            "detection can never fire (A4/B6)"
        )


def test_detect_misconception_matches_baited_answer(monkeypatch):
    """_detect_misconception must match an answer that voices a seeded misconception."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    pipeline.digest(_input(), conn=conn, candidate=CANDIDATE, session_id="s")

    concept_rows = conn.execute(
        "SELECT id, slug FROM concepts WHERE source='digested'"
    ).fetchall()
    assert concept_rows

    found_match = False
    for cid, slug in concept_rows:
        misconceptions = repo.get_misconceptions_for_concept(conn, cid)
        for m in misconceptions:
            hint = m.get("detect_hint")
            if not hint:
                continue
            # Build a "baited" answer that contains a word from detect_hint
            # so the regex can match.
            keyword = re.split(r"[|\\()\[\]]+", hint)[0].strip()
            if not keyword:
                continue
            baited = f"I think {keyword} means something else entirely"
            detected = _detect_misconception(baited, misconceptions)
            if detected is not None:
                found_match = True
                break
        if found_match:
            break

    assert found_match, (
        "No misconception's detect_hint matched a baited answer — "
        "either detect_hint is missing or its regex cannot match (A4/B6)"
    )
