"""Tests for the recommend-next skill (spec §6.5).

Graph fixture:
    A (id=1) ──prereq──> B (id=2) ──prereq──> C (id=3)
                         B (id=2) ──prereq──> D (id=4)

All run offline (no LLM, no network, $0).  recommend_next is fully deterministic
and makes no LLM calls, so no provider env var is needed here.
"""
import sqlite3

import pytest

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.recommend.recommend_next import recommend_next
from litnav.recommend.contract import Recommendation


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_db() -> tuple[sqlite3.Connection, str]:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "s", topic="test")

    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'a', 'Alpha')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (2, 'b', 'Beta')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (3, 'c', 'Gamma')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (4, 'd', 'Delta')")

    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) "
        "VALUES (1, 2, 'prerequisite')"
    )
    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) "
        "VALUES (2, 3, 'prerequisite')"
    )
    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) "
        "VALUES (2, 4, 'prerequisite')"
    )
    conn.commit()
    return conn, "s"


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_nothing_mastered_only_roots_eligible():
    """With no mastery, only root concepts (no prereqs) are eligible."""
    conn, sid = _make_db()
    recs = recommend_next(conn, sid, mastery_threshold=0.75)

    eligible = {r.concept_id for r in recs if r.eligible}
    blocked = {r.concept_id for r in recs if not r.eligible}

    assert eligible == {1}, f"Only A (no prereqs) should be eligible; got {eligible}"
    assert 2 in blocked, "B blocked until A mastered"
    assert 3 in blocked, "C blocked until B mastered"
    assert 4 in blocked, "D blocked until B mastered"


def test_mastering_a_makes_b_eligible():
    """After mastering A, B's prereq is satisfied — B becomes eligible."""
    conn, sid = _make_db()
    repo.upsert_learner_state(conn, sid, 1, mastery=0.9, confidence=1.0, n_observations=1)

    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)
    rec_ids = {r.concept_id for r in recs}
    eligible = {r.concept_id for r in recs if r.eligible}

    # A is mastered → must be excluded
    assert 1 not in rec_ids, "Mastered concept A must not appear"
    # B's prereq (A) is mastered → eligible
    assert 2 in eligible, "B should be eligible after A is mastered"
    # C and D still blocked (B not mastered)
    assert 3 not in eligible, "C still blocked"
    assert 4 not in eligible, "D still blocked"


def test_ranking_higher_unlock_comes_first():
    """B (unlocks C and D = score 2) should outrank C and D (score 0) when eligible."""
    conn, sid = _make_db()
    # Master A so B becomes eligible
    repo.upsert_learner_state(conn, sid, 1, mastery=1.0, confidence=1.0, n_observations=1)

    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)
    eligible = [r for r in recs if r.eligible]

    assert eligible, "There should be at least one eligible concept"
    assert eligible[0].concept_id == 2, (
        f"B (score=2) should be first eligible; got id={eligible[0].concept_id}"
    )
    assert eligible[0].score == 2.0, (
        f"B unlocks C and D → score 2.0; got {eligible[0].score}"
    )


def test_mastered_concepts_excluded():
    """Mastered concepts must not appear in recommendations."""
    conn, sid = _make_db()
    repo.upsert_learner_state(conn, sid, 1, mastery=1.0, confidence=1.0, n_observations=2)
    repo.upsert_learner_state(conn, sid, 2, mastery=0.8, confidence=1.0, n_observations=2)

    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)
    rec_ids = {r.concept_id for r in recs}

    assert 1 not in rec_ids, "Mastered A must be excluded"
    assert 2 not in rec_ids, "Mastered B must be excluded"
    # C and D should be present and eligible
    assert 3 in rec_ids, "C should appear"
    assert 4 in rec_ids, "D should appear"
    eligible = {r.concept_id for r in recs if r.eligible}
    assert 3 in eligible and 4 in eligible, "C and D eligible when their prereq B is mastered"


def test_k_cap_limits_results():
    """k parameter caps the returned list."""
    conn, sid = _make_db()
    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=2)
    assert len(recs) <= 2, f"Expected at most 2 recommendations; got {len(recs)}"


def test_eligible_first_ordering():
    """Eligible concepts appear before non-eligible ones in the result list."""
    conn, sid = _make_db()
    repo.upsert_learner_state(conn, sid, 1, mastery=0.9, confidence=1.0, n_observations=1)

    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)
    seen_ineligible = False
    for r in recs:
        if not r.eligible:
            seen_ineligible = True
        if seen_ineligible and r.eligible:
            pytest.fail("Eligible concept appeared after an ineligible one")


def test_reason_strings_well_formed():
    """Reason strings follow the specified format."""
    conn, sid = _make_db()
    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)
    for r in recs:
        if r.eligible:
            assert "Ready now" in r.reason, f"eligible reason malformed: {r.reason!r}"
        else:
            assert "Blocked" in r.reason, f"ineligible reason malformed: {r.reason!r}"
            assert "needs" in r.reason, f"ineligible reason must name prereqs: {r.reason!r}"


def test_return_type_is_recommendation_dataclass():
    """recommend_next returns Recommendation dataclass instances."""
    conn, sid = _make_db()
    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=5)
    assert all(isinstance(r, Recommendation) for r in recs)
    for r in recs:
        assert isinstance(r.concept_id, int)
        assert isinstance(r.slug, str)
        assert isinstance(r.name, str)
        assert isinstance(r.score, float)
        assert isinstance(r.eligible, bool)


def test_no_concepts_returns_empty():
    """An empty graph returns an empty list."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "empty", topic="empty")
    recs = recommend_next(conn, "empty")
    assert recs == []
