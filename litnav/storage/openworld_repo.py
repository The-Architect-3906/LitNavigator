"""Repo writers for the open-world tables: learner_goal, review_queue, digest_cache."""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3


# ── learner_goal ──────────────────────────────────────────────────────────────
def set_goal(conn: sqlite3.Connection, session_id: str, goal_text: str, goal_type: str,
             target_concepts: list[int]) -> None:
    """Upsert the session's learning goal (one row per session)."""
    conn.execute(
        "INSERT INTO learner_goal (session_id, goal_text, goal_type, target_concepts_json) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "goal_text=excluded.goal_text, goal_type=excluded.goal_type, "
        "target_concepts_json=excluded.target_concepts_json",
        (session_id, goal_text, goal_type, json.dumps(target_concepts)),
    )
    conn.commit()


def get_goal(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute(
        "SELECT goal_text, goal_type, target_concepts_json FROM learner_goal WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return {"goal_text": row[0], "goal_type": row[1],
            "target_concepts": json.loads(row[2]) if row[2] else []}


# ── review_queue (FSRS spacing) ───────────────────────────────────────────────
def enqueue_review(conn: sqlite3.Connection, session_id: str, concept_id: int, *,
                   due_at: str, fsrs_state: dict) -> None:
    """Schedule (or reschedule) a concept's spaced review. One row per (session, concept)."""
    conn.execute(
        "INSERT INTO review_queue (session_id, concept_id, due_at, fsrs_state_json) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(session_id, concept_id) DO UPDATE SET "
        "due_at=excluded.due_at, fsrs_state_json=excluded.fsrs_state_json",
        (session_id, concept_id, due_at, json.dumps(fsrs_state)),
    )
    conn.commit()


def due_reviews(conn: sqlite3.Connection, session_id: str, now: str) -> list[dict]:
    """Concepts whose due_at <= now, oldest first."""
    rows = conn.execute(
        "SELECT concept_id, due_at, fsrs_state_json FROM review_queue "
        "WHERE session_id=? AND due_at<=? ORDER BY due_at",
        (session_id, now),
    ).fetchall()
    return [{"concept_id": r[0], "due_at": r[1],
             "fsrs_state": json.loads(r[2]) if r[2] else {}} for r in rows]


# ── digest_cache (demand-driven memoization; no prediction) ───────────────────
def cache_get(conn: sqlite3.Connection, slice_key: str) -> dict | None:
    row = conn.execute(
        "SELECT status, graph_version, built_at, human_checked, model_key "
        "FROM digest_cache WHERE slice_key=?",
        (slice_key,),
    ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "graph_version": row[1], "built_at": row[2],
            "human_checked": bool(row[3]), "model_key": row[4]}


def cache_put(conn: sqlite3.Connection, slice_key: str, *, graph_version: int = 1,
              human_checked: bool = False, model_key: str | None = None) -> None:
    """Mark a digested slice as cached. Upsert keyed by slice_key."""
    conn.execute(
        "INSERT INTO digest_cache (slice_key, status, graph_version, built_at, human_checked, model_key) "
        "VALUES (?, 'cached', ?, ?, ?, ?) "
        "ON CONFLICT(slice_key) DO UPDATE SET "
        "status='cached', graph_version=excluded.graph_version, built_at=excluded.built_at, "
        "human_checked=excluded.human_checked, model_key=excluded.model_key",
        (slice_key, graph_version, _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
         1 if human_checked else 0, model_key),
    )
    conn.commit()
