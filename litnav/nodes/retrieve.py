from __future__ import annotations

import sqlite3

from litnav.state import NavState


def retrieve_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    rows = conn.execute(
        "SELECT id, text, paper_id FROM paper_chunks WHERE concept_id=?",
        (concept_id,),
    ).fetchall()
    evidence = [{"chunk_id": r[0], "text": r[1], "paper_id": r[2], "score": 1.0} for r in rows]
    return {"current_evidence": evidence}
