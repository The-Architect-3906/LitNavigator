from __future__ import annotations

import sqlite3

from litnav.state import NavState


def teach_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    evidence = state["current_evidence"]

    row = conn.execute("SELECT name FROM concepts WHERE id=?", (concept_id,)).fetchone()
    concept_name = row[0] if row else f"concept {concept_id}"

    if evidence:
        chunk = evidence[0]
        message = (
            f"**{concept_name}**\n\n"
            f"{chunk['text']}\n\n"
            f"*(Source: chunk {chunk['chunk_id']})*"
        )
        cited_chunks = [chunk["chunk_id"]]
    else:
        message = f"**{concept_name}** — no evidence found for this concept yet."
        cited_chunks = []

    teaching_turn = {
        "concept_id": concept_id,
        "strategy": "direct",
        "message": message,
        "cited_chunks": cited_chunks,
    }
    return {
        "history": [{"event": "teach", "concept_id": concept_id, "cited_chunks": cited_chunks}],
    }
