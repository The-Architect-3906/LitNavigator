"""Tests for _norm_chunk_id returning None on unresolvable ids (not valid_ids[0]).

TDD: written BEFORE the fix is applied — currently _norm_chunk_id returns valid_ids[0].
"""
from __future__ import annotations

import pytest
from litnav.digest.pipeline import _norm_chunk_id


VALID = ["c0", "c1", "c2", "c3"]


def test_norm_chunk_id_exact_match():
    """Exact match still resolves correctly."""
    assert _norm_chunk_id("c2", VALID) == "c2"


def test_norm_chunk_id_zero_indexed_int_resolves():
    """0-indexed bare int -> c0."""
    assert _norm_chunk_id("0", VALID) == "c0"


def test_norm_chunk_id_one_indexed_int_resolves():
    """1-indexed int '1' -> c1 (it tries c1 first, which exists)."""
    assert _norm_chunk_id("1", VALID) == "c1"


def test_norm_chunk_id_c_prefix_resolves():
    """'c2' format resolves to c2."""
    assert _norm_chunk_id("c2", VALID) == "c2"


def test_norm_chunk_id_returns_none_for_junk():
    """Junk id (not a real chunk, not parseable index) → None, NOT c0."""
    result = _norm_chunk_id("BAD_HALLUCINATED_ID", VALID)
    assert result is None, f"Expected None but got {result!r} — old behaviour returned c0"


def test_norm_chunk_id_returns_none_for_out_of_range_index():
    """Index beyond the chunk count → None, NOT c0."""
    result = _norm_chunk_id("c99", VALID)
    assert result is None, f"Expected None but got {result!r}"


def test_norm_chunk_id_returns_none_for_empty_valid_ids():
    """Empty valid_ids → None (unchanged behaviour)."""
    assert _norm_chunk_id("c0", []) is None


def test_norm_chunk_id_returns_none_for_none_raw():
    """None raw → None, NOT c0."""
    result = _norm_chunk_id(None, VALID)
    assert result is None, f"Expected None but got {result!r}"
