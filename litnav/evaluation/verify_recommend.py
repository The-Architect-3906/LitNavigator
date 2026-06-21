"""G-recommend (offline determinism gate) — recommend-next skill (spec §6.5).

Seeds a small concept graph (A→B→C prereq chain + side concept D off B),
sets learner mastery, and asserts eligibility/ranking/exclusion invariants.
No LLM — fully deterministic, $0.
"""
from __future__ import annotations

import os
import sqlite3

os.environ["LITNAV_LLM_PROVIDER"] = "none"

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.recommend.recommend_next import recommend_next


def _seed_db() -> tuple[sqlite3.Connection, str]:
    """Seed a small graph:

        A (id=1) ──prereq──> B (id=2) ──prereq──> C (id=3)
                             B (id=2) ──prereq──> D (id=4)

    D is a side concept: only prereq is B, not in the A→B→C chain.
    So the unlock potential:
      A → unlocks B (which gates C and D) = 1 direct downstream
      B → unlocks C and D = 2 direct downstream
    """
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "sess1", topic="test")

    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'a', 'Alpha')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (2, 'b', 'Beta')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (3, 'c', 'Gamma')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (4, 'd', 'Delta')")

    # A → B → C chain
    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (1, 2, 'prerequisite')"
    )
    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (2, 3, 'prerequisite')"
    )
    # B → D side branch
    conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (2, 4, 'prerequisite')"
    )
    conn.commit()
    return conn, "sess1"


def main() -> int:
    # ── G-recommend-1: nothing mastered → only roots (A) are eligible ──────────
    conn, sid = _seed_db()
    recs = recommend_next(conn, sid, mastery_threshold=0.75, k=10)

    eligible_ids = {r.concept_id for r in recs if r.eligible}
    ineligible_ids = {r.concept_id for r in recs if not r.eligible}

    # A has no prereqs → eligible; B, C, D all have unmastered prereqs → blocked
    assert eligible_ids == {1}, (
        f"With nothing mastered, only A (root) should be eligible; got {eligible_ids}"
    )
    assert ineligible_ids == {2, 3, 4}, (
        f"B, C, D should all be blocked; got {ineligible_ids}"
    )
    print("G-recommend PASS: nothing mastered → only root concept A is eligible")

    # ── G-recommend-2: master A → B becomes eligible ───────────────────────────
    conn2, sid2 = _seed_db()
    repo.upsert_learner_state(conn2, sid2, 1, mastery=0.9, confidence=1.0, n_observations=1)

    recs2 = recommend_next(conn2, sid2, mastery_threshold=0.75, k=10)
    eligible2 = {r.concept_id for r in recs2 if r.eligible}
    mastered_present = [r for r in recs2 if r.concept_id == 1]  # A is mastered, must be excluded

    assert 1 not in eligible2, "Mastered concept A must not appear in recommendations"
    assert mastered_present == [], "Mastered concept A must be excluded entirely"
    assert 2 in eligible2, "After mastering A, B must become eligible"
    assert 3 not in eligible2, "C still blocked (B not mastered)"
    assert 4 not in eligible2, "D still blocked (B not mastered)"
    print("G-recommend PASS: mastering A makes B eligible; A excluded; C and D still blocked")

    # ── G-recommend-3: ranking — higher-unlock concepts rank first ──────────────
    conn3, sid3 = _seed_db()
    # Master A so B and other root concepts are eligible; B unlocks 2 (C and D)
    repo.upsert_learner_state(conn3, sid3, 1, mastery=0.9, confidence=1.0, n_observations=1)

    recs3 = recommend_next(conn3, sid3, mastery_threshold=0.75, k=10)
    eligible3 = [r for r in recs3 if r.eligible]

    # B should be first among eligible (score=2, unlocks C and D)
    assert eligible3, "There should be at least one eligible concept"
    assert eligible3[0].concept_id == 2, (
        f"B (unlocks 2) should rank first among eligible; got concept_id={eligible3[0].concept_id}"
    )
    assert eligible3[0].score == 2.0, (
        f"B's score should be 2.0 (unlocks C and D); got {eligible3[0].score}"
    )
    print("G-recommend PASS: B (unlocks 2 concepts) ranks above lower-unlock eligible concepts")

    # ── G-recommend-4: mastered concepts excluded from results ─────────────────
    conn4, sid4 = _seed_db()
    # Master A and B
    repo.upsert_learner_state(conn4, sid4, 1, mastery=1.0, confidence=1.0, n_observations=2)
    repo.upsert_learner_state(conn4, sid4, 2, mastery=0.8, confidence=1.0, n_observations=2)

    recs4 = recommend_next(conn4, sid4, mastery_threshold=0.75, k=10)
    rec_ids4 = {r.concept_id for r in recs4}

    assert 1 not in rec_ids4, "Mastered A must be excluded"
    assert 2 not in rec_ids4, "Mastered B must be excluded"
    # C and D should appear as eligible (both prereqs A and B mastered)
    assert 3 in rec_ids4, "C should appear (B mastered)"
    assert 4 in rec_ids4, "D should appear (B mastered)"
    eligible4 = {r.concept_id for r in recs4 if r.eligible}
    assert 3 in eligible4 and 4 in eligible4, "C and D should be eligible when B is mastered"
    print("G-recommend PASS: mastered concepts excluded; C and D eligible when A and B are mastered")

    # ── G-recommend-5: reason strings are well-formed ──────────────────────────
    conn5, sid5 = _seed_db()
    recs5 = recommend_next(conn5, sid5, mastery_threshold=0.75, k=10)
    for r in recs5:
        if r.eligible:
            assert "Ready now" in r.reason, f"eligible reason malformed: {r.reason!r}"
            assert "unlocks" in r.reason, f"eligible reason must mention unlocks: {r.reason!r}"
        else:
            assert "Blocked" in r.reason, f"ineligible reason malformed: {r.reason!r}"
            assert "needs" in r.reason, f"ineligible reason must name prereqs: {r.reason!r}"
    print("G-recommend PASS: reason strings are well-formed for all recommendations")

    print("G-recommend: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
