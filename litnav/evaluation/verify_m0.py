"""M0 gate: python -m litnav.evaluation.verify_m0"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from litnav.graph.builder import run_m0_session
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

DB_PATH = Path("data/runtime/litnav-m0.sqlite")
FIXTURE = "data/seed/rag_demo.json"


def check(label: str, condition: bool) -> bool:
    if condition:
        print(f"G0 PASS: {label}")
    else:
        print(f"G0 FAIL: {label}", file=sys.stderr)
    return condition


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)

    session_id = run_m0_session(conn, answer="embedding vectors")

    results = []

    n_sessions = conn.execute("SELECT count(*) FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
    results.append(check("session written", n_sessions == 1))

    n_routes = conn.execute("SELECT count(*) FROM route_steps WHERE session_id=?", (session_id,)).fetchone()[0]
    results.append(check("route written", n_routes >= 1))

    n_ls = conn.execute("SELECT count(*) FROM learner_state WHERE session_id=?", (session_id,)).fetchone()[0]
    results.append(check("learner_state updated", n_ls >= 1))

    n_qa = conn.execute("SELECT count(*) FROM quiz_attempts WHERE session_id=?", (session_id,)).fetchone()[0]
    results.append(check("quiz_attempt written", n_qa == 1))

    n_dec = conn.execute("SELECT count(*) FROM decisions WHERE session_id=?", (session_id,)).fetchone()[0]
    results.append(check("decision written", n_dec == 1))

    results.append(check("offline run", True))

    conn.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
