from __future__ import annotations

import os
import sqlite3

from litnav.state import NavState


def _concept_tagged(conn: sqlite3.Connection, concept_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, text, paper_id FROM paper_chunks WHERE concept_id=? "
        "ORDER BY CASE WHEN substr(id, 1, 3)='cx_' THEN 1 ELSE 0 END, rowid",
        (concept_id,),
    ).fetchall()
    return [{"chunk_id": r[0], "text": r[1], "paper_id": r[2], "score": 1.0} for r in rows]


def retrieve_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    tagged = _concept_tagged(conn, concept_id)

    # Opt-in semantic retrieval (M4): only when LITNAV_RETRIEVAL=vector, an index exists,
    # and embeddings are available. Restricted to the current concept's chunks so the tutor
    # never teaches one concept with another's evidence (hybrid: concept filter, then rerank
    # within the concept by query similarity). Falls back to concept-tagged evidence
    # otherwise, so the default path and all offline gates are unchanged.
    if os.getenv("LITNAV_RETRIEVAL") == "vector":
        from litnav.retrieval.vector import semantic_search
        row = conn.execute("SELECT name FROM concepts WHERE id=?", (concept_id,)).fetchone()
        query = row[0] if row else state.get("topic", "")
        hits = semantic_search(conn, query, top_k=3, concept_id=concept_id)
        if hits:
            return {"current_evidence": [
                {"chunk_id": h["chunk_id"], "text": h["text"],
                 "paper_id": h["paper_id"], "score": h["score"]} for h in hits]}

    return {"current_evidence": tagged}
