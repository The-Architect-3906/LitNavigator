"""Unit tests for resolve_evidence_chunk — all branches of the precedence ladder.

TDD: tests written BEFORE the implementation exists (they must fail first).
"""
from __future__ import annotations

import math
import pytest

# The function we're implementing — import will fail until the module exists.
from litnav.digest.evidence import resolve_evidence_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine(a: list[float], b: list[float]) -> float:
    n = _norm(a) * _norm(b)
    return _dot(a, b) / n if n else 0.0


# Fake embed_fn that returns a fixed 3-d vector per text.
# We use a simple keyword-based scheme: each dim corresponds to a keyword.
# This is deterministic and fully offline.
KEYWORDS = ["attention", "transformer", "recurrent"]


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Fake embedding: each dim = 1.0 if keyword present, else 0.0."""
    result = []
    for t in texts:
        t_low = t.lower()
        result.append([1.0 if kw in t_low else 0.0 for kw in KEYWORDS])
    return result


CHUNKS = {
    "c0": "The attention mechanism scores each token against all others.",
    "c1": "Transformer architecture relies on multi-head attention.",
    "c2": "Recurrent networks process sequences step by step.",
    "c3": "Gradient descent optimises the model parameters.",
}


# ---------------------------------------------------------------------------
# Branch 1: quote matches EXACTLY ONE chunk → "verified" / "quote-exact"
# ---------------------------------------------------------------------------

def test_quote_exact_one_match_verified_when_id_agrees():
    """Emitted id also resolves to the same chunk → label 'verified'."""
    chunk_id, label = resolve_evidence_chunk(
        quote="scores each token against all others",
        emitted_id="c0",
        chunks=CHUNKS,
    )
    assert chunk_id == "c0"
    assert label == "verified"


def test_quote_exact_one_match_quote_exact_when_id_disagrees():
    """Quote uniquely identifies c0; emitted id says c2 → label 'quote-exact'."""
    chunk_id, label = resolve_evidence_chunk(
        quote="scores each token against all others",
        emitted_id="c2",
        chunks=CHUNKS,
    )
    assert chunk_id == "c0"
    assert label == "quote-exact"


def test_quote_normalization_collapses_whitespace_and_case():
    """Quote with extra whitespace and mixed case still matches."""
    chunk_id, label = resolve_evidence_chunk(
        quote="  Scores  Each Token Against  ALL  Others  ",
        emitted_id="c0",
        chunks=CHUNKS,
    )
    assert chunk_id == "c0"
    assert label == "verified"


# ---------------------------------------------------------------------------
# Branch 2: quote matches MULTIPLE chunks → "quote-multi"
# ---------------------------------------------------------------------------

def test_quote_multi_uses_id_to_disambiguate():
    """'attention' appears in both c0 and c1; emitted id c1 wins."""
    chunk_id, label = resolve_evidence_chunk(
        quote="attention",
        emitted_id="c1",
        chunks=CHUNKS,
    )
    assert chunk_id == "c1"
    assert label == "quote-multi"


def test_quote_multi_falls_back_to_first_match_when_id_not_among_matches():
    """'attention' in c0 and c1; emitted id c2 not in matches → first match (c0)."""
    chunk_id, label = resolve_evidence_chunk(
        quote="attention",
        emitted_id="c2",
        chunks=CHUNKS,
    )
    assert chunk_id == "c0"
    assert label == "quote-multi"


# ---------------------------------------------------------------------------
# Branch 3: quote matches NO chunk, but emitted id resolves to a real id → "id-only"
# ---------------------------------------------------------------------------

def test_id_only_when_quote_missing_but_id_valid():
    """No quote (empty string), but id is real → id-only."""
    chunk_id, label = resolve_evidence_chunk(
        quote="",
        emitted_id="c2",
        chunks=CHUNKS,
    )
    assert chunk_id == "c2"
    assert label == "id-only"


def test_id_only_when_quote_not_found_in_any_chunk():
    """Junk quote, valid id → id-only (id corroborates)."""
    chunk_id, label = resolve_evidence_chunk(
        quote="xyzzy completely absent text",
        emitted_id="c3",
        chunks=CHUNKS,
    )
    assert chunk_id == "c3"
    assert label == "id-only"


# ---------------------------------------------------------------------------
# Branch 4: embedding fallback → "embedding"
# ---------------------------------------------------------------------------

def test_embedding_fallback_hits_when_above_threshold():
    """Quote that doesn't appear as substring but shares keywords with a chunk.
    The fake embed_fn maps keywords to dims; 'transformer' is in c1 → high cosine.
    Query 'transformer' → [0,1,0]; c1 has 'transformer+attention' → [1,1,0].
    cosine([0,1,0],[1,1,0]) = 1/sqrt(2) ≈ 0.707 ≥ 0.55 → resolves via embedding.
    """
    # Use a quote that won't substring-match but whose keyword IS in a chunk.
    # "transformer model" is NOT a verbatim substring of c1 (which has "Transformer architecture")
    # but our fake embed returns [0,1,0] for it because 'transformer' is in KEYWORDS.
    # We add a chunk set where the quote truly isn't a substring but shares embed dims.
    local_chunks = {
        "c0": "The attention mechanism scores each token.",
        "c1": "Multi-head transformer layers dominate modern NLP.",
        "c2": "Recurrent networks use hidden state propagation.",
    }
    # Query: "transformer-based approach" — not a substring of c1 ("Multi-head transformer layers…")
    # but fake embed gives [0,1,0] because 'transformer' is a keyword.
    # c1 embed: "transformer" present → [0,1,0]; cosine([0,1,0],[0,1,0]) = 1.0 ≥ 0.55
    chunk_id, label = resolve_evidence_chunk(
        quote="transformer-based approach to language modelling",
        emitted_id="BAD_ID",
        chunks=local_chunks,
        embed_fn=_fake_embed,
        sim_min=0.55,
    )
    assert chunk_id is not None
    assert chunk_id in local_chunks
    assert label == "embedding"


def test_embedding_fallback_degrades_to_paper_level_below_threshold():
    """Even if embedding finds a best match, if below sim_min → paper-level."""
    # With sim_min=0.999 (impossibly high), no chunk can match.
    chunk_id, label = resolve_evidence_chunk(
        quote="zzz_not_in_any_chunk",
        emitted_id="BAD_ID",
        chunks=CHUNKS,
        embed_fn=_fake_embed,
        sim_min=0.999,
    )
    assert chunk_id is None
    assert label == "paper-level"


# ---------------------------------------------------------------------------
# Branch 5: paper-level → (None, "paper-level")
# ---------------------------------------------------------------------------

def test_paper_level_when_no_quote_no_id_no_embed():
    """No quote, bad id, no embed_fn → paper-level (not c0!)."""
    chunk_id, label = resolve_evidence_chunk(
        quote="",
        emitted_id="BAD_ID",
        chunks=CHUNKS,
        embed_fn=None,
    )
    assert chunk_id is None
    assert label == "paper-level"


def test_paper_level_when_all_options_exhausted():
    """Junk quote, junk id, no embed_fn → paper-level."""
    chunk_id, label = resolve_evidence_chunk(
        quote="this text does not appear in any chunk whatsoever",
        emitted_id="c99",
        chunks=CHUNKS,
        embed_fn=None,
    )
    assert chunk_id is None
    assert label == "paper-level"


def test_paper_level_when_chunks_empty():
    """Empty chunks dict → paper-level, no crash."""
    chunk_id, label = resolve_evidence_chunk(
        quote="anything",
        emitted_id="c0",
        chunks={},
        embed_fn=None,
    )
    assert chunk_id is None
    assert label == "paper-level"


# ---------------------------------------------------------------------------
# Critical invariant: NEVER collapse to the first chunk by default
# ---------------------------------------------------------------------------

def test_never_defaults_to_first_chunk_for_bad_id():
    """_norm_chunk_id used to return valid_ids[0]; resolve_evidence_chunk must NOT."""
    chunk_id, label = resolve_evidence_chunk(
        quote="",
        emitted_id="c99_invalid",
        chunks=CHUNKS,
        embed_fn=None,
    )
    # MUST NOT be c0 (the first chunk), must be None or genuinely resolved
    assert chunk_id is None
    assert label == "paper-level"
