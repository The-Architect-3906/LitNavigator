"""Tests for Task 3 & 4 of B1 fix:
- evidence_quote field in extraction prompt (schema change)
- _write_graph uses resolve_evidence_chunk (quote-authority + id corroboration)
- quiz inherits its keypoint's resolved chunk (not independent resolution)

TDD: tests written BEFORE implementation — must fail first.
"""
from __future__ import annotations

import sqlite3
import pytest

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline, extract


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    return c


# A DigestInput with 3 distinct chunks — enough to route to distinct chunks.
def _make_di(chunks=None):
    if chunks is None:
        chunks = [
            "The attention mechanism computes a weighted sum of values.",
            "Transformer models use positional encodings to handle sequence order.",
            "Recurrent networks maintain a hidden state across timesteps.",
        ]
    return DigestInput("ml", [SourceDoc("arxiv", "2401.00001", "Test Paper", "http://x", chunks)], [])


# Candidate used for offline replay — includes evidence_quote field.
CANDIDATE_WITH_QUOTE = {
    "concepts": [
        {"slug": "attention", "name": "Attention Mechanism", "domain": "ml", "frontier_flag": None},
        {"slug": "positional_enc", "name": "Positional Encoding", "domain": "ml", "frontier_flag": None},
    ],
    "keypoints": [
        {
            "kp_id": "kp_attn_1",
            "concept_slug": "attention",
            "name": "Attention weighted sum",
            "objective": "Explain how attention computes a weighted sum of values.",
            "evidence_chunk_id": "c0",
            # evidence_quote: a verbatim span from chunk c0
            "evidence_quote": "computes a weighted sum of values",
            "bloom_level": "recall",
        },
        {
            "kp_id": "kp_pos_1",
            "concept_slug": "positional_enc",
            "name": "Positional encodings for order",
            "objective": "Explain how positional encodings convey sequence order in Transformers.",
            "evidence_chunk_id": "c1",
            # evidence_quote: verbatim span from chunk c1
            "evidence_quote": "positional encodings to handle sequence order",
            "bloom_level": "recall",
        },
    ],
    "prereq_edges": [],
    "similarity_edges": [],
    "quiz_seeds": [
        {
            "concept_slug": "attention",
            "question": "What does the attention mechanism compute?",
            "answer_key": "a weighted sum of values",
            "bloom_level": "recall",
            "keypoint_id": "kp_attn_1",
        },
        {
            "concept_slug": "positional_enc",
            "question": "What do positional encodings provide?",
            "answer_key": "sequence order information",
            "bloom_level": "recall",
            "keypoint_id": "kp_pos_1",
        },
    ],
    "judge_labels": {},
    "misconceptions": [],
}


# ---------------------------------------------------------------------------
# Test 3a: extraction prompt includes evidence_quote field
# ---------------------------------------------------------------------------

def test_extraction_prompt_includes_evidence_quote_field(monkeypatch):
    """The prompt sent to the LLM must request evidence_quote in the keypoints schema."""
    captured_prompts = []

    def fake_complete_json(prompt, **kwargs):
        captured_prompts.append(prompt)
        return kwargs.get("fallback", {})

    import litnav.llm.router as router_mod
    monkeypatch.setattr(router_mod, "complete_json", fake_complete_json)
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")  # trigger live path
    monkeypatch.setenv("LITNAV_LLM_API_KEY", "fake")

    c = _make_conn()
    di = _make_di()
    try:
        extract.extract_concepts(di, candidate=CANDIDATE_WITH_QUOTE, session_id="s", conn=c)
    except Exception:
        pass  # we only need to capture the prompt

    assert captured_prompts, "No prompt captured"
    full_prompt = captured_prompts[0]
    assert "evidence_quote" in full_prompt, (
        f"'evidence_quote' not in extraction prompt.\n"
        f"Prompt: {full_prompt[:500]!r}"
    )


# ---------------------------------------------------------------------------
# Test 3b: _write_graph uses quote to resolve chunk (not just emitted id)
# ---------------------------------------------------------------------------

def test_write_graph_uses_quote_to_resolve_chunk(monkeypatch):
    """When keypoint has evidence_quote matching chunk c0, it should be stored with c0
    even if emitted_id is a junk value ('BAD_ID').

    Before the fix: _norm_chunk_id('BAD_ID') returns None; no resolution at all.
    After the fix: resolve_evidence_chunk uses the quote → c0 (quote-exact).
    """
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _make_conn()

    # Keypoint with a JUNK emitted_id but a good quote that spans c0.
    candidate = {
        **CANDIDATE_WITH_QUOTE,
        "keypoints": [
            {
                "kp_id": "kp_attn_1",
                "concept_slug": "attention",
                "name": "Attention weighted sum",
                "objective": "Explain how attention computes a weighted sum of values.",
                "evidence_chunk_id": "BAD_HALLUCINATED_ID",   # junk id
                "evidence_quote": "computes a weighted sum of values",  # quote IS in c0
                "bloom_level": "recall",
            },
        ],
        "concepts": [
            {"slug": "attention", "name": "Attention Mechanism", "domain": "ml", "frontier_flag": None},
        ],
        "quiz_seeds": [],
        "misconceptions": [],
    }
    di = _make_di()
    pipeline.digest(di, conn=c, candidate=candidate, session_id="s")

    # Fetch the written keypoint and assert it got c0, not None.
    rows = c.execute("SELECT id, evidence_chunk_id FROM keypoints").fetchall()
    kp_row = {r[0]: r[1] for r in rows}
    assert "kp_attn_1" in kp_row, f"keypoint not written: {list(kp_row.keys())}"
    resolved = kp_row["kp_attn_1"]

    assert resolved == "c0", (
        f"Expected c0 (quote-resolved) but got {resolved!r}. "
        "The resolver should use the quote to identify c0 despite the junk emitted_id."
    )


# ---------------------------------------------------------------------------
# Test 4: quiz inherits its keypoint's resolved chunk
# ---------------------------------------------------------------------------

def test_quiz_inherits_keypoint_chunk(monkeypatch):
    """After digest, each quiz item's evidence_chunk_id must equal its keypoint's
    resolved evidence_chunk_id — no independent re-resolution."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _make_conn()
    di = _make_di()
    pipeline.digest(di, conn=c, candidate=CANDIDATE_WITH_QUOTE, session_id="s")

    # Get all keypoints and quiz items from the DB.
    kp_rows = c.execute("SELECT id, evidence_chunk_id FROM keypoints").fetchall()
    kp_chunk_by_id = {row[0]: row[1] for row in kp_rows}

    quiz_rows = c.execute(
        "SELECT keypoint_id, evidence_chunk_id FROM quiz_items WHERE keypoint_id IS NOT NULL"
    ).fetchall()

    assert quiz_rows, "No quiz items with keypoint_id found"

    for kp_id, quiz_chunk in quiz_rows:
        expected_chunk = kp_chunk_by_id.get(kp_id)
        assert quiz_chunk == expected_chunk, (
            f"Quiz for kp_id={kp_id!r} has evidence_chunk_id={quiz_chunk!r}, "
            f"but its keypoint resolved to {expected_chunk!r}. "
            "Quiz must inherit its keypoint's chunk."
        )


# ---------------------------------------------------------------------------
# Test 3c: honest paper-level when quote and id both unresolvable
# ---------------------------------------------------------------------------

def test_write_graph_stores_none_not_c0_when_unresolvable(monkeypatch):
    """When both quote and emitted_id are junk, keypoint evidence_chunk_id must be
    None (paper-level), not c0."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _make_conn()

    candidate = {
        "concepts": [
            {"slug": "attention", "name": "Attention", "domain": "ml", "frontier_flag": None},
        ],
        "keypoints": [
            {
                "kp_id": "kp_attn_bad",
                "concept_slug": "attention",
                "name": "Bad evidence",
                "objective": "Test.",
                "evidence_chunk_id": "BAD_ID_99",   # junk
                "evidence_quote": "",               # no quote
                "bloom_level": "recall",
            },
        ],
        "prereq_edges": [], "similarity_edges": [],
        "quiz_seeds": [], "judge_labels": {}, "misconceptions": [],
    }
    di = _make_di()
    pipeline.digest(di, conn=c, candidate=candidate, session_id="s")

    rows = c.execute("SELECT id, evidence_chunk_id FROM keypoints").fetchall()
    kp_chunk = {r[0]: r[1] for r in rows}
    assert "kp_attn_bad" in kp_chunk, f"keypoint not written; found: {list(kp_chunk.keys())}"

    resolved = kp_chunk["kp_attn_bad"]
    # Must NOT be c0 (old default collapse), and the quote/id were both junk.
    # However the fallback round-robin may assign a chunk for concept-coverage;
    # that's the paper_chunks assignment, NOT the keypoint's evidence_chunk_id.
    # The keypoint's evidence_chunk_id should be None.
    assert resolved is None, (
        f"Expected None for unresolvable keypoint, got {resolved!r}. "
        "Old behaviour was to collapse to c0."
    )
