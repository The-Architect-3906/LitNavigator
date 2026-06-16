from __future__ import annotations

import sqlite3

from litnav.state import NavState
from litnav.storage import repo


def check_node(state: NavState, conn: sqlite3.Connection) -> dict:
    """Socratic check. Draws a parallel quiz form for the concept, preferring one not yet
    used this concept so pre/post comparisons use equal-difficulty but distinct items."""
    concept_id = state["current_concept_id"]
    used = list(state.get("used_quiz_ids") or [])

    items = repo.get_parallel_quiz_items(conn, concept_id, exclude_ids=used)
    if not items:
        return {"current_quiz_item": None}

    quiz_item = items[0]
    if quiz_item["id"] not in used:
        used.append(quiz_item["id"])

    return {"current_quiz_item": quiz_item, "used_quiz_ids": used}
