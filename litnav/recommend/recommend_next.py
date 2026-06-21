"""Deterministic, graph-derived "what to learn next" recommender (spec §6.5).

No LLM — all logic is rule-computed from the concept graph and learner mastery stored in
the domain DB.  Fully offline ($0).
"""
from __future__ import annotations

import sqlite3
from typing import NamedTuple

from litnav.recommend.contract import Recommendation


def recommend_next(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    mastery_threshold: float = 0.75,
    k: int = 5,
) -> list[Recommendation]:
    """Return up to *k* recommended concepts for the learner in *session_id*.

    Eligible concepts (all prereqs mastered) come first, sorted by:
      1. score desc  (number of not-yet-mastered concepts this concept directly unlocks)
      2. fewer remaining unmastered prereqs
      3. concept id (stable tie-break)

    Non-eligible concepts follow, in the same secondary/tertiary order.
    Mastered concepts are excluded entirely.
    """
    # ── load concepts ─────────────────────────────────────────────────────────
    concepts: dict[int, tuple[str, str]] = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT id, slug, name FROM concepts").fetchall()
    }

    # ── load prerequisite edges (prereq → target) ─────────────────────────────
    # prereqs_of[target] = set of prereq concept ids
    # targets_of[prereq] = set of target concept ids
    prereqs_of: dict[int, set[int]] = {cid: set() for cid in concepts}
    targets_of: dict[int, set[int]] = {cid: set() for cid in concepts}

    for prereq_id, target_id in conn.execute(
        "SELECT prereq_concept, target_concept FROM concept_edges WHERE edge_type='prerequisite'"
    ).fetchall():
        if prereq_id in concepts and target_id in concepts:
            prereqs_of[target_id].add(prereq_id)
            targets_of[prereq_id].add(target_id)

    # ── load learner mastery (default 0.0 for unknown) ────────────────────────
    mastery_by_cid: dict[int, float] = {}
    for cid, mastery in conn.execute(
        "SELECT concept_id, mastery FROM learner_state WHERE session_id=?",
        (session_id,),
    ).fetchall():
        mastery_by_cid[cid] = mastery

    # ── compute mastered set ──────────────────────────────────────────────────
    mastered: set[int] = {
        cid for cid in concepts
        if mastery_by_cid.get(cid, 0.0) >= mastery_threshold
    }

    # ── build candidate list (not yet mastered) ───────────────────────────────
    candidates = [cid for cid in concepts if cid not in mastered]

    # ── score each candidate ──────────────────────────────────────────────────
    # score = number of not-yet-mastered downstream concepts this concept unlocks
    def _unlock_count(cid: int) -> float:
        return float(sum(1 for t in targets_of[cid] if t not in mastered))

    def _remaining_prereqs(cid: int) -> int:
        return sum(1 for p in prereqs_of[cid] if p not in mastered)

    results: list[Recommendation] = []
    for cid in candidates:
        slug, name = concepts[cid]
        unmastered_prereqs = [p for p in prereqs_of[cid] if p not in mastered]
        eligible = len(unmastered_prereqs) == 0
        score = _unlock_count(cid)

        if eligible:
            reason = f"Ready now — unlocks {int(score)} concept{'s' if int(score) != 1 else ''}"
        else:
            prereq_names = ", ".join(
                concepts[p][1] for p in sorted(unmastered_prereqs)
                if p in concepts
            )
            reason = f"Blocked — needs {prereq_names} first"

        results.append(Recommendation(
            concept_id=cid,
            slug=slug,
            name=name,
            score=score,
            reason=reason,
            eligible=eligible,
        ))

    # ── sort: eligible first, then by score desc, remaining prereqs asc, id asc ─
    results.sort(key=lambda r: (
        0 if r.eligible else 1,
        -r.score,
        _remaining_prereqs(r.concept_id),
        r.concept_id,
    ))

    return results[:k]
