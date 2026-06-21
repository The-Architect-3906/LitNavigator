"""FSRS-lite spacing for the review queue + delayed retention probe (spec §6.3, risk B).
Deterministic: `now` is passed in (ISO string), never read from the clock here."""
from __future__ import annotations
import datetime as _dt
import sqlite3
from litnav.storage import openworld_repo

_BASE_DAYS = 1.0
_MAX_DAYS = 365.0


def interval_days(mastery: float) -> float:
    """Cadence inverse to forgetting: higher recall prob (mastery) -> longer interval.
    Fast-forward at P(mastery) >= 0.95 (over-practice avoidance)."""
    m = max(0.0, min(mastery, 0.999))
    days = _BASE_DAYS / (1.0 - m)            # ∝ 1/(1-recall_prob)
    if m >= 0.95:
        days *= 2.0                          # over-practice fast-forward
    return round(min(days, _MAX_DAYS), 2)


def _add_days(now_iso: str, days: float) -> str:
    base = _dt.datetime.fromisoformat(now_iso)
    return (base + _dt.timedelta(days=days)).isoformat(timespec="seconds")


def schedule_review(conn: sqlite3.Connection, session_id: str, concept_id: int, *,
                    mastery: float, now: str) -> None:
    d = interval_days(mastery)
    openworld_repo.enqueue_review(conn, session_id, concept_id,
                                  due_at=_add_days(now, d),
                                  fsrs_state={"mastery_at_schedule": round(mastery, 4), "interval_days": d})


def due_probes(conn: sqlite3.Connection, session_id: str, now: str) -> list[dict]:
    return openworld_repo.due_reviews(conn, session_id, now)


def log_retention(conn: sqlite3.Connection, session_id: str, concept_id: int, *,
                  predicted: float, actual: float, probed_at: str) -> None:
    conn.execute("INSERT INTO retention_log (session_id, concept_id, predicted, actual, probed_at) "
                 "VALUES (?,?,?,?,?)", (session_id, concept_id, predicted, actual, probed_at))
    conn.commit()
