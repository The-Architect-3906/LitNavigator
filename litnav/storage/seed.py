from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def seed_demo_data(conn: sqlite3.Connection, fixture_path: str) -> None:
    data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))

    for c in data["concepts"]:
        conn.execute(
            "INSERT OR IGNORE INTO concepts (id, slug, name, description, is_demo_core, frontier_flag) "
            "VALUES (?,?,?,?,?,?)",
            (c["id"], c["slug"], c["name"], c.get("description"),
             c.get("is_demo_core", 0), c.get("frontier_flag")),
        )

    for p in data["papers"]:
        conn.execute(
            "INSERT OR IGNORE INTO papers (id, arxiv_id, title, year) VALUES (?,?,?,?)",
            (p["id"], p.get("arxiv_id"), p["title"], p.get("year")),
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
            "(id, concept_id, question, answer_key, qtype, difficulty, "
            " evidence_chunk_id, source_paper_id, targets_misconception) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (q["id"], q["concept_id"], q["question"], q["answer_key"],
             q.get("qtype", "mcq"), q.get("difficulty", 1),
             q.get("evidence_chunk_id"), q.get("source_paper_id"),
             q.get("targets_misconception")),
        )

    # Optional: misconception library (present from M2 onward).
    for m in data.get("misconceptions", []):
        conn.execute(
            "INSERT OR IGNORE INTO misconceptions "
            "(id, concept_id, wrong_model, correct_model, detect_hint, reteach_strategy, "
            " source, confidence, evidence_chunk_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (m["id"], m["concept_id"], m.get("wrong_model"), m.get("correct_model"),
             m.get("detect_hint"), m.get("reteach_strategy"),
             m.get("source", "curated"), m.get("confidence", 1.0),
             m.get("evidence_chunk_id")),
        )

    conn.commit()
