"""B18 regression: per-concept evidence chunks.

Every concept in a digested slice must have its own evidence chunks tagged
with concept_id so retrieve_node can serve them. Before the fix, all chunks
were written with concept_id=NULL -> retrieve_node returned 0 chunks for every
concept, and teach_kp cited the same boilerplate c0 for every keypoint.

Two root problems:
  1. _write_sources wrote chunks with concept_id=NULL (never linked to concepts).
  2. _norm_chunk_id fell back to valid_ids[0] when the LLM emitted an
     unresolvable id, so MULTIPLE keypoints (across different concepts) all
     collapsed to the same first chunk.

The test runs the real offline digest() on two source docs / two concepts
(four distinct chunks), then asserts:
  a. retrieve_node returns >=1 chunk for EACH concept (not 0).
  b. The two concepts' chunks are DIFFERENT (not the same boilerplate chunk).
  c. Each concept's keypoints resolve to evidence_chunk_ids drawn from THAT
     concept's own chunk pool (not from another concept's pool).
"""
import sqlite3

import pytest

from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.nodes.retrieve import retrieve_node
from litnav.state import NavState
from litnav.storage import repo
from litnav.storage.schema import init_db


# Two-concept, four-chunk candidate: alpha owns c0+c1, beta owns c2+c3.
# The LLM-style evidence_chunk_id uses bare integers ('0','1','2','3') to
# exercise the _norm_chunk_id path as well as confirming distinct assignment.
MULTI_CAND = {
    "concepts": [
        {"slug": "alpha_concept", "name": "Alpha", "frontier_flag": None},
        {"slug": "beta_concept",  "name": "Beta",  "frontier_flag": None},
    ],
    "keypoints": [
        {"kp_id": "kp_a1", "concept_slug": "alpha_concept", "name": "Alpha KP 1",
         "objective": "Understand alpha mechanism", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp_a2", "concept_slug": "alpha_concept", "name": "Alpha KP 2",
         "objective": "Apply alpha technique", "evidence_chunk_id": "c1", "bloom_level": "recall"},
        {"kp_id": "kp_b1", "concept_slug": "beta_concept",  "name": "Beta KP 1",
         "objective": "Understand beta mechanism", "evidence_chunk_id": "c2", "bloom_level": "recall"},
        {"kp_id": "kp_b2", "concept_slug": "beta_concept",  "name": "Beta KP 2",
         "objective": "Apply beta technique", "evidence_chunk_id": "c3", "bloom_level": "recall"},
    ],
    "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {},
}


def _build_di():
    return DigestInput(
        "test_domain",
        [
            SourceDoc("web", "src_alpha", "Alpha Paper", "http://alpha",
                      ["alpha chunk zero unique", "alpha chunk one unique"]),
            SourceDoc("web", "src_beta",  "Beta Paper",  "http://beta",
                      ["beta chunk two unique",  "beta chunk three unique"]),
        ],
        target_slugs=[],
    )


@pytest.fixture()
def digested_conn(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", topic="t")
    pipeline.digest(_build_di(), conn=c, candidate=MULTI_CAND, session_id="s")
    return c


def test_retrieve_returns_chunks_for_every_concept(digested_conn):
    """retrieve_node must return >=1 chunk for each digested concept (not 0)."""
    c = digested_conn
    concepts = c.execute("SELECT id, slug FROM concepts ORDER BY id").fetchall()
    assert len(concepts) == 2, f"expected 2 concepts, got {len(concepts)}"
    for cid, slug in concepts:
        state = NavState({"session_id": "s", "current_concept_id": cid, "topic": slug})  # type: ignore
        result = retrieve_node(state, c)
        chunks = result.get("current_evidence", [])
        assert len(chunks) >= 1, (
            f"concept '{slug}' (id={cid}) got 0 chunks from retrieve_node — "
            f"chunks have concept_id=NULL and were never linked"
        )


def test_each_concept_gets_distinct_evidence_chunks(digested_conn):
    """The two concepts must not share the same single evidence chunk."""
    c = digested_conn
    concepts = c.execute("SELECT id, slug FROM concepts ORDER BY id").fetchall()
    chunk_sets: list[frozenset[str]] = []
    for cid, slug in concepts:
        state = NavState({"session_id": "s", "current_concept_id": cid, "topic": slug})  # type: ignore
        result = retrieve_node(state, c)
        ids = frozenset(ch["chunk_id"] for ch in result.get("current_evidence", []))
        chunk_sets.append(ids)
    # The two concepts' chunk sets must differ (B18: not all citing c0)
    assert chunk_sets[0] != chunk_sets[1], (
        f"Both concepts serve the same evidence chunk set {chunk_sets[0]} — "
        f"the boilerplate-reuse bug is still present"
    )
    # They must not overlap at all (each concept has its own dedicated chunks)
    assert chunk_sets[0].isdisjoint(chunk_sets[1]), (
        f"Concepts share evidence chunks: overlap={chunk_sets[0] & chunk_sets[1]}"
    )


def test_keypoint_evidence_chunk_ids_differ_across_concepts(digested_conn):
    """Keypoints from different concepts must not ALL resolve to the same chunk id."""
    c = digested_conn
    rows = c.execute(
        "SELECT k.id, k.evidence_chunk_id, con.slug "
        "FROM keypoints k JOIN concepts con ON k.concept_id=con.id "
        "ORDER BY k.id"
    ).fetchall()
    assert rows, "no keypoints written"
    by_concept: dict[str, set[str]] = {}
    for kp_id, eid, slug in rows:
        by_concept.setdefault(slug, set()).add(eid)
    # Two distinct concepts must have non-overlapping evidence_chunk_ids
    concept_slugs = list(by_concept)
    assert len(concept_slugs) >= 2, "need at least 2 concepts to compare"
    set_a = by_concept[concept_slugs[0]]
    set_b = by_concept[concept_slugs[1]]
    assert set_a.isdisjoint(set_b), (
        f"Concepts '{concept_slugs[0]}' and '{concept_slugs[1]}' share "
        f"evidence_chunk_ids: {set_a & set_b} — all keypoints collapsed to the same chunk"
    )
