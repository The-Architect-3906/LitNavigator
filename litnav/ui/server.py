"""Thin FastAPI trace panel — the judge-facing recordable artifact.

Left: teaching/quiz transcript (tutor turns + decisions).
Right: route + route_version, decision rationale, cited evidence, mastery/confidence,
       and a three-color concept strip (consensus / contested / open).

Run:  python -m litnav.ui.server        (defaults to data/runtime/litnav.sqlite)
The CLI demo runner (litnav.app) populates that DB; the panel renders it read-only.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from litnav.config import DEMO_DB_PATH
from litnav.ui.trace import build_trace

app = FastAPI(title="LitNavigator trace panel")

_TEMPLATES = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _connect() -> sqlite3.Connection:
    # Default to the demo DB the CLI runner populates; honor an explicit override.
    return sqlite3.connect(os.getenv("LITNAV_DB_PATH", DEMO_DB_PATH))


def _list_sessions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, topic, status, created_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    return [{"id": r[0], "topic": r[1], "status": r[2], "created_at": r[3]} for r in rows]


@app.get("/sessions/{session_id}/trace")
def trace_json(session_id: str):
    conn = _connect()
    try:
        return JSONResponse(build_trace(conn, session_id))
    finally:
        conn.close()


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_page(session_id: str):
    conn = _connect()
    try:
        data = build_trace(conn, session_id)
    finally:
        conn.close()
    return _TEMPLATES.get_template("index.html").render(session_id=session_id, **data)


@app.get("/", response_class=HTMLResponse)
def index():
    conn = _connect()
    try:
        sessions = _list_sessions(conn)
    finally:
        conn.close()
    links = "".join(
        f'<li><a href="/sessions/{s["id"]}">{s["topic"]} — {s["id"][:8]} ({s["status"]})</a></li>'
        for s in sessions
    ) or "<li>No sessions yet. Run <code>python -m litnav.app demo-m2 --answer cot</code>.</li>"
    return f"<html><body style='font-family:system-ui;margin:2rem'><h1>LitNavigator sessions</h1><ul>{links}</ul></body></html>"


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
