from __future__ import annotations

import sqlite3

from litnav.state import NavState


def diagnose_node(state: NavState, conn: sqlite3.Connection) -> dict:
    # A12: when coming from the keypoint path, current_concept_id may not yet be updated
    # because assess_decider fires before advance_kp clears concept_progress.  Fall back
    # to concept_progress.concept_id so the detour targets the right concept.
    cp = state.get("concept_progress") or {}
    concept_id = state.get("current_concept_id") or cp.get("concept_id")
    threshold = state.get("mastery_threshold", 0.8)
    dag = state.get("concept_dag") or {}
    learner_state = state.get("learner_state") or {}

    # If concept_dag doesn't have this concept's prereqs, fall back to a DB query.
    if concept_id in dag:
        prereqs = dag[concept_id]
    else:
        rows = conn.execute(
            "SELECT prereq_concept FROM concept_edges WHERE target_concept=? AND edge_type='prerequisite'",
            (concept_id,),
        ).fetchall()
        prereqs = [r[0] for r in rows]
    unmastered = [
        p for p in prereqs
        if learner_state.get(p, {}).get("mastery", 0.0) < threshold
    ]

    if unmastered:
        # pick the lowest unmastered prereq (by id for determinism)
        missing_id = min(unmastered)
        row = conn.execute("SELECT slug, name FROM concepts WHERE id=?", (missing_id,)).fetchone()
        missing_slug = row[0] if row else str(missing_id)
        missing_name = row[1] if row else str(missing_id)
        diagnosis = {
            "blocked_concept_id": concept_id,
            "missing_concept_id": missing_id,
            "missing_slug": missing_slug,
            "missing_name": missing_name,
        }
    else:
        diagnosis = {"blocked_concept_id": concept_id, "missing_concept_id": None}

    return {
        "diagnosis": diagnosis,
        "history": [{"event": "diagnose", **diagnosis}],
    }
