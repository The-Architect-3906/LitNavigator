"""Thin FastAPI trace panel — the judge-facing recordable artifact.

Left: teaching/quiz transcript (tutor turns + decisions).
Right: route + route_version, decision rationale, cited evidence, mastery/confidence,
       and a three-color concept strip (consensus / contested / open).

Run:  python -m litnav.ui.server        (defaults to data/runtime/litnav.sqlite)
The CLI demo runner (litnav.app) populates that DB; the panel renders it read-only.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from litnav.config import DEMO_CKPT_PATH, DEMO_DB_PATH
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession
from litnav.ui.trace import build_trace

# In-memory live tutor sessions (single-process demo). Keyed by session id.
_TUTORS: dict[str, TutorSession] = {}

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
        # Open the most recent session's panel directly (the last demo you ran).
        if sessions:
            data = build_trace(conn, sessions[0]["id"])
            return _TEMPLATES.get_template("index.html").render(session_id=sessions[0]["id"], **data)
    finally:
        conn.close()
    return ("<html><body style='font-family:system-ui;margin:2rem'>"
            "<h1>LitNavigator</h1><p>No sessions yet. Run "
            "<code>python -m litnav.app demo-m2 --answer cot</code> or "
            "<code>python -m litnav.app demo-m3</code>, then refresh.</p></body></html>")


# ── Interactive tutor (B): real human-in-the-loop over the graph ───────────────
# GET-based forms keep this dependency-free (no python-multipart); fine for a local demo.

def _start_tutor(fixture: str, target_ids: list[int], pending_induction: dict | None) -> str:
    db = Path(DEMO_DB_PATH); db.parent.mkdir(parents=True, exist_ok=True); db.unlink(missing_ok=True)
    ck = Path(DEMO_CKPT_PATH); ck.unlink(missing_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, fixture)
    topic = json.loads(Path(fixture).read_text(encoding="utf-8"))["topic"]
    sid = str(uuid.uuid4())
    ts = TutorSession(conn, sqlite3.connect(str(ck), check_same_thread=False), sid)
    ts.start(topic, target_concept_ids=target_ids, pending_induction=pending_induction,
             mastery_threshold=0.75)
    _TUTORS[sid] = ts
    return sid


@app.get("/tutor", response_class=HTMLResponse)
def tutor_home():
    return (
        "<html><body style='font-family:system-ui;margin:2rem;max-width:40rem'>"
        "<h1>LitNavigator — interactive tutor</h1>"
        "<p>Pick a session. The tutor teaches a concept, quizzes you, and adapts to your answer.</p>"
        "<p><a href='/tutor/start?mode=react'><b>Teach me ReAct</b></a> "
        "— misconception &rarr; reteach demo (try answering \"it's just chain of thought\" first).</p>"
        "<p><a href='/tutor/start?mode=induce'><b>I keep seeing &lsquo;multi-agent debate&rsquo;</b></a> "
        "— off-skeleton: the tutor induces the scaffold from the papers, then teaches it.</p>"
        "</body></html>"
    )


@app.get("/tutor/start")
def tutor_start(mode: str = "react"):
    if mode == "induce":
        cand = json.loads(Path("data/seed/agents_m3.json").read_text(encoding="utf-8"))["induction"]
        sid = _start_tutor("data/seed/agents_m3.json", [], cand)
    else:
        sid = _start_tutor("data/seed/agents_m2.json", [1], None)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ts = _TUTORS.get(sid)
    if ts is None:
        return RedirectResponse("/tutor", status_code=303)
    return _TEMPLATES.get_template("tutor.html").render(sid=sid, **ts.current())


@app.get("/tutor/{sid}/answer")
def tutor_answer(sid: str, answer: str = ""):
    ts = _TUTORS.get(sid)
    if ts is not None and answer.strip():
        ts.answer(answer)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
