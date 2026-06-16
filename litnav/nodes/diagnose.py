from __future__ import annotations

import sqlite3

from litnav.state import NavState


def diagnose_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    threshold = state.get("mastery_threshold", 0.8)
    dag = state["concept_dag"]
    learner_state = state["learner_state"]

    prereqs = dag.get(concept_id, [])
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
