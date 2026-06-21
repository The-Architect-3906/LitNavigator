from __future__ import annotations

import datetime as _dt
import sqlite3

from litnav.assess import spacing as _spacing
from litnav.state import NavState
from litnav.storage import repo


def advance_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    route_version = state["route_version"]
    quiz_result = state.get("quiz_result") or {}

    route = [dict(s) for s in state["route"]]
    for step in route:
        if step["concept_id"] == concept_id and step["status"] == "pending":
            step["status"] = "done"
            repo.update_route_step_status(
                conn, session_id, route_version, step["step_id"], "done"
            )
            break

    mastery = state["learner_state"].get(concept_id, {}).get("mastery", 0.0)
    rationale = (
        f"Concept {concept_id} mastery={mastery:.3f} >= threshold or conceded. "
        f"Quiz score={quiz_result.get('score', '?')}. Advancing."
    )
    repo.record_decision(
        conn, session_id, route_version, "advance", "advance", rationale,
        state_snapshot={"concept_id": concept_id, "mastery": mastery},
    )

    # FSRS-lite: schedule a delayed retention probe for the mastered concept (best-effort,
    # never breaks the advance flow; spec §6.3, risk B).
    try:
        _spacing.schedule_review(
            conn, session_id, concept_id,
            mastery=mastery,
            now=_dt.datetime.now().isoformat(timespec="seconds"),
        )
    except Exception:
        pass

    return {
        "route": route,
        "rationale": rationale,
        "history": [{"event": "advance", "concept_id": concept_id, "mastery": mastery}],
    }
