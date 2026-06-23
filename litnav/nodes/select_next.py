from __future__ import annotations

from litnav.state import NavState

TERMINAL_STATUSES = {"done", "conceded"}


def select_next_node(state: NavState) -> dict:
    pending = [s for s in state["route"] if s["status"] == "pending"]
    if not pending:
        return {"current_concept_id": None}
    # Reset per-concept teaching state so a previous concept's reteach strategy doesn't leak
    # into this one's first teach. Only the new-concept path passes through here; reteach loops
    # straight back to teach (reteach -> teach), so an in-progress reteach keeps its strategy.
    # B11: clear the previous concept's decision/rationale so the glass box doesn't surface a
    # stale "concede" (or other terminal decision) while teaching the next concept.
    return {"current_concept_id": pending[0]["concept_id"],
            "current_strategy": None, "current_cited_chunks": [],
            "decision": None, "rationale": None}


def route_after_select(state: NavState) -> str:
    return "__end__" if state["current_concept_id"] is None else "retrieve"
