"""lecture_node — orientation-only pass for a concept that has no quiz.

When a routed concept has no quiz item, the tutor can still teach it from cited evidence,
but it cannot assess the learner. Rather than reuse `advance` (which records a
mastery-based "advancing" rationale), this node marks the step `lectured` and records an
honest decision that makes NO mastery claim. Keeps multi-concept routes (e.g. intent routes)
moving without pretending an unassessed concept was mastered.
"""
from __future__ import annotations

import sqlite3

from litnav.state import NavState
from litnav.storage import repo


def lecture_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    route_version = state["route_version"]

    route = [dict(s) for s in state["route"]]
    for step in route:
        if step["concept_id"] == concept_id and step["status"] == "pending":
            step["status"] = "lectured"
            repo.update_route_step_status(
                conn, session_id, route_version, step["step_id"], "lectured"
            )
            break

    rationale = (
        f"Concept {concept_id}: orientation only — taught from cited evidence, but it has no "
        f"quiz, so the learner was not assessed and no mastery is claimed. Moving on."
    )
    repo.record_decision(
        conn, session_id, route_version, "lecture", "lecture", rationale,
        state_snapshot={"concept_id": concept_id, "lecture_only": True},
    )

    return {
        "route": route,
        "rationale": rationale,
        "history": [{"event": "lecture", "concept_id": concept_id}],
    }
