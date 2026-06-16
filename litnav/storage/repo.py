from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def create_session(conn: sqlite3.Connection, session_id: str, topic: str, user_id: str = "demo") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, user_id, topic, status) VALUES (?,?,?,?)",
        (session_id, user_id, topic, "active"),
    )
    conn.commit()


def upsert_learner_state(
    conn: sqlite3.Connection,
    session_id: str,
    concept_id: int,
    mastery: float,
    confidence: float,
    n_observations: int,
    held_misconceptions: list[str] | None = None,
    tried_strategies: list[str] | None = None,
    depth: str = "recall",
    evidence: list | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO learner_state
            (session_id, concept_id, mastery, confidence, n_observations,
             held_misconceptions, tried_strategies, depth, evidence, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(session_id, concept_id) DO UPDATE SET
            mastery=excluded.mastery,
            confidence=excluded.confidence,
            n_observations=excluded.n_observations,
            held_misconceptions=excluded.held_misconceptions,
            tried_strategies=excluded.tried_strategies,
            depth=excluded.depth,
            evidence=excluded.evidence,
            updated_at=excluded.updated_at
        """,
        (
            session_id, concept_id, mastery, confidence, n_observations,
            json.dumps(held_misconceptions or []),
            json.dumps(tried_strategies or []),
            depth,
            json.dumps(evidence or []),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def write_route_steps(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    steps: list[dict],
) -> None:
    for step in steps:
        conn.execute(
            """
            INSERT OR IGNORE INTO route_steps
                (session_id, route_version, step_id, concept_id, paper_id, status, reason, confidence)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                session_id, route_version, step["step_id"], step["concept_id"],
                step.get("paper_id"), step.get("status", "pending"),
                step.get("reason", ""), step.get("confidence", 1.0),
            ),
        )
    conn.commit()


def update_route_step_status(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    step_id: str,
    status: str,
) -> None:
    conn.execute(
        "UPDATE route_steps SET status=? WHERE session_id=? AND route_version=? AND step_id=?",
        (status, session_id, route_version, step_id),
    )
    conn.commit()


def record_quiz_attempt(
    conn: sqlite3.Connection,
    session_id: str,
    quiz_item_id: int,
    user_answer: str,
    score: float,
    feedback: str,
    concept_score_delta: dict | None = None,
    detected_misconception: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO quiz_attempts
            (session_id, quiz_item_id, user_answer, score, feedback, concept_score_delta, detected_misconception)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            session_id, quiz_item_id, user_answer, score, feedback,
            json.dumps(concept_score_delta or {}),
            detected_misconception,
        ),
    )
    conn.commit()


def record_decision(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    from_node: str,
    decision: str,
    rationale: str,
    state_snapshot: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO decisions
            (session_id, route_version, from_node, decision, rationale, state_snapshot)
        VALUES (?,?,?,?,?,?)
        """,
        (
            session_id, route_version, from_node, decision, rationale,
            json.dumps(state_snapshot or {}),
        ),
    )
    conn.commit()


def get_quiz_item(conn: sqlite3.Connection, concept_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, concept_id, question, answer_key, evidence_chunk_id, source_paper_id "
        "FROM quiz_items WHERE concept_id=? LIMIT 1",
        (concept_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "concept_id": row[1], "question": row[2],
        "answer_key": row[3], "evidence_chunk_id": row[4], "source_paper_id": row[5],
    }


def get_concept_prereqs(conn: sqlite3.Connection, concept_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT prereq_concept FROM concept_edges WHERE target_concept=? AND edge_type='prerequisite'",
        (concept_id,),
    ).fetchall()
    return [r[0] for r in rows]


def get_learner_mastery(conn: sqlite3.Connection, session_id: str, concept_id: int) -> float | None:
    row = conn.execute(
        "SELECT mastery FROM learner_state WHERE session_id=? AND concept_id=?",
        (session_id, concept_id),
    ).fetchone()
    return row[0] if row else None
