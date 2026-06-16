from __future__ import annotations

import sqlite3


def retrieve_evidence(conn: sqlite3.Connection, concept_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, text, paper_id FROM paper_chunks WHERE concept_id=?",
        (concept_id,),
    ).fetchall()
    return [{"chunk_id": r[0], "text": r[1], "paper_id": r[2], "score": 1.0} for r in rows]
