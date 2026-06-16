from __future__ import annotations

import sqlite3

from litnav.state import NavState


def check_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    row = conn.execute(
        "SELECT id, concept_id, question, answer_key, evidence_chunk_id, source_paper_id "
        "FROM quiz_items WHERE concept_id=? LIMIT 1",
        (concept_id,),
    ).fetchone()
    if row is None:
        quiz_item = None
    else:
        quiz_item = {
            "id": row[0], "concept_id": row[1], "question": row[2],
            "answer_key": row[3], "evidence_chunk_id": row[4], "source_paper_id": row[5],
        }
    return {"current_quiz_item": quiz_item}
