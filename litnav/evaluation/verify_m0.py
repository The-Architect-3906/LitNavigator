"""M0 gate: python -m litnav.evaluation.verify_m0"""
from __future__ import annotations

import sqlite3
import socket
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from litnav.graph.builder import run_m0_session
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

DB_PATH = Path("data/runtime/litnav-m0.sqlite")
FIXTURE = "data/seed/rag_demo.json"


class OfflineRunError(RuntimeError):
    """Raised when a supposedly offline gate attempts network access."""


def check(label: str, condition: bool) -> bool:
    if condition:
        print(f"G0 PASS: {label}")
    else:
        print(f"G0 FAIL: {label}", file=sys.stderr)
    return condition


@contextmanager
def offline_guard():
    def deny_network(*args, **kwargs):
        raise OfflineRunError(f"Network access attempted with args={args!r}")

    with (
        mock.patch("socket.create_connection", side_effect=deny_network),
        mock.patch.object(socket.socket, "connect", autospec=True, side_effect=deny_network),
        mock.patch.object(socket.socket, "connect_ex", autospec=True, side_effect=deny_network),
    ):
        yield


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)

    session_id = None
    offline_ok = True
    try:
        with offline_guard():
            session_id = run_m0_session(conn, answer="embedding vectors")
    except OfflineRunError:
        offline_ok = False

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

    results.append(check("offline run", offline_ok))

    conn.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
