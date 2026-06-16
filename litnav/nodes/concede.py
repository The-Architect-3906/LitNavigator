from __future__ import annotations

import sqlite3

from litnav.state import NavState
from litnav.storage import repo


def concede_node(state: NavState, conn: sqlite3.Connection) -> dict:
    """Honest termination: reteach is exhausted and no prerequisite is missing, yet the concept
    has not been mastered. Flag low confidence, say so plainly (S5), mark the step conceded,
    and move on — do not loop and do not pretend it was taught."""
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    route_version = state["route_version"]

    learner_state = dict(state["learner_state"])
    cs = dict(learner_state.get(concept_id, {}))
    mastery = cs.get("mastery", 0.0)
    n_obs = cs.get("n_observations", 0)
    # Honesty signal: this estimate is explicitly low-confidence.
    cs["confidence"] = round(min(cs.get("confidence", 0.0), 0.3), 2)
    learner_state[concept_id] = cs
    repo.upsert_learner_state(
        conn, session_id, concept_id,
        mastery=mastery, confidence=cs["confidence"], n_observations=n_obs,
        held_misconceptions=cs.get("held_misconceptions", []),
        tried_strategies=cs.get("tried_strategies", []),
    )

    route = [dict(s) for s in state["route"]]
    for step in route:
        if step["concept_id"] == concept_id and step["status"] == "pending":
            step["status"] = "conceded"
            repo.update_route_step_status(conn, session_id, route_version, step["step_id"], "conceded")
            break

    rationale = (
        f"I switched explanations {len(cs.get('tried_strategies', []))} times and concept "
        f"{concept_id} still has not landed (mastery={mastery:.3f}). Marking it not-yet-mastered "
        f"with low confidence ({cs['confidence']}) — you can overrule me — and moving on rather "
        f"than looping. We can come back to it."
    )
    repo.record_decision(
        conn, session_id, route_version, "tutor_router", "concede", rationale,
        state_snapshot={"concept_id": concept_id, "mastery": mastery, "confidence": cs["confidence"]},
    )

    return {
        "learner_state": learner_state,
        "route": route,
        "rationale": rationale,
        "history": [{"event": "concede", "concept_id": concept_id, "mastery": mastery}],
    }
