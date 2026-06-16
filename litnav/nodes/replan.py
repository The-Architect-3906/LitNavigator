from __future__ import annotations

import sqlite3

from litnav.state import NavState
from litnav.storage import repo


def replan_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    diagnosis = state.get("diagnosis") or {}
    missing_id = diagnosis.get("missing_concept_id")
    blocked_id = diagnosis.get("blocked_concept_id")

    route = [dict(s) for s in state["route"]]

    # Check if missing concept is already in the route
    existing_ids = {s["concept_id"] for s in route}
    if missing_id is None or missing_id in existing_ids:
        # Nothing to insert; just increment version to record the event
        new_version = state["route_version"] + 1
        repo.write_route_steps(conn, session_id, new_version, route)
        rationale = f"No new prereq to insert (already in route or none found)."
        repo.record_decision(conn, session_id, new_version, "replan", "replan_noop", rationale)
        return {"route": route, "route_version": new_version, "rationale": rationale,
                "history": [{"event": "replan_noop", "route_version": new_version}]}

    # Insert missing concept before the blocked concept
    insert_before = next(
        (i for i, s in enumerate(route)
         if s["concept_id"] == blocked_id and s["status"] == "pending"),
        len(route),
    )

    step_id = f"route-ins-{missing_id:03d}"
    row = conn.execute("SELECT name FROM concepts WHERE id=?", (missing_id,)).fetchone()
    missing_name = row[0] if row else str(missing_id)

    new_step = {
        "step_id": step_id,
        "concept_id": missing_id,
        "paper_id": None,
        "reason": f"Inserted: prerequisite of concept {blocked_id} ({missing_name}), revealed by quiz gap.",
        "status": "pending",
        "confidence": 1.0,
    }
    route.insert(insert_before, new_step)

    new_version = state["route_version"] + 1
    repo.write_route_steps(conn, session_id, new_version, route)

    rationale = (
        f"Quiz revealed {missing_name} (id={missing_id}) is a missing prerequisite of "
        f"concept {blocked_id}. Inserted before it. route_version → {new_version}."
    )
    repo.record_decision(
        conn, session_id, new_version, "replan", "replan",
        rationale,
        state_snapshot={"inserted": missing_id, "before": blocked_id},
    )

    return {
        "route": route,
        "route_version": new_version,
        "rationale": rationale,
        "history": [{"event": "replan", "inserted": missing_id,
                     "before": blocked_id, "route_version": new_version}],
    }
