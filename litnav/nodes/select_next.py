from __future__ import annotations

from litnav.state import NavState

TERMINAL_STATUSES = {"done", "conceded"}


def select_next_node(state: NavState) -> dict:
    pending = [s for s in state["route"] if s["status"] == "pending"]
    if not pending:
        return {"current_concept_id": None}
    return {"current_concept_id": pending[0]["concept_id"]}


def route_after_select(state: NavState) -> str:
    return "__end__" if state["current_concept_id"] is None else "retrieve"
