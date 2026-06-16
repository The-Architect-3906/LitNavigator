from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def seed_demo_data(conn: sqlite3.Connection, fixture_path: str) -> None:
    data = json.loads(Path(fixture_path).read_text())

    for c in data["concepts"]:
        conn.execute(
            "INSERT OR IGNORE INTO concepts (id, slug, name, frontier_flag) VALUES (?,?,?,?)",
            (c["id"], c["slug"], c["name"], c.get("frontier_flag")),
        )

    for p in data["papers"]:
        conn.execute(
            "INSERT OR IGNORE INTO papers (id, title, year) VALUES (?,?,?)",
            (p["id"], p["title"], p.get("year")),
        )

    for ch in data["chunks"]:
        conn.execute(
            "INSERT OR IGNORE INTO paper_chunks (id, paper_id, concept_id, text) VALUES (?,?,?,?)",
            (ch["id"], ch["paper_id"], ch["concept_id"], ch["text"]),
        )

    for e in data["edges"]:
        conn.execute(
            "INSERT OR IGNORE INTO concept_edges "
            "(prereq_concept, target_concept, edge_type, source, confidence) VALUES (?,?,?,?,?)",
            (e["prereq_concept"], e["target_concept"], e["edge_type"], e["source"], e["confidence"]),
        )

    for q in data["quiz_items"]:
        conn.execute(
            "INSERT OR IGNORE INTO quiz_items "
            "(id, concept_id, question, answer_key, evidence_chunk_id, source_paper_id) VALUES (?,?,?,?,?,?)",
            (q["id"], q["concept_id"], q["question"], q["answer_key"],
             q.get("evidence_chunk_id"), q.get("source_paper_id")),
        )

    conn.commit()
