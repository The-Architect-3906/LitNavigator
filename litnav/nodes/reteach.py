from __future__ import annotations

import sqlite3

from litnav.state import RETEACH_STRATEGIES, NavState
from litnav.storage import repo


def reteach_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    route_version = state["route_version"]

    cs = state["learner_state"].get(concept_id, {})
    tried = list(cs.get("tried_strategies", []))
    held = list(cs.get("held_misconceptions", []))

    # Pick the first strategy not yet tried; fall back to the last one if all are used.
    new_strategy = next((s for s in RETEACH_STRATEGIES if s not in tried), RETEACH_STRATEGIES[-1])

    reteach_count = dict(state.get("reteach_count", {}))
    reteach_count[concept_id] = reteach_count.get(concept_id, 0) + 1

    # Anchor the reteach to the held misconception's correct_model when we know it.
    correct_model = ""
    if held:
        for m in repo.get_misconceptions_for_concept(conn, concept_id):
            if m["id"] == held[0]:
                correct_model = m.get("correct_model") or ""
                break

    rationale = (
        f"Misconception {held[0] if held else '(none)'} still held after strategy "
        f"'{tried[-1] if tried else 'direct'}'. Switching to '{new_strategy}' "
        f"(attempt {reteach_count[concept_id]}/2)."
        + (f" Target correct model: {correct_model}" if correct_model else "")
    )
    repo.record_decision(
        conn, session_id, route_version, "tutor_router", "reteach", rationale,
        state_snapshot={"concept_id": concept_id, "new_strategy": new_strategy,
                        "reteach_count": reteach_count[concept_id]},
    )

    return {
        "current_strategy": new_strategy,
        "reteach_count": reteach_count,
        "rationale": rationale,
        "history": [{"event": "reteach_decision", "concept_id": concept_id,
                     "new_strategy": new_strategy, "count": reteach_count[concept_id]}],
    }
