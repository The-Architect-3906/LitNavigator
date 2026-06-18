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

from litnav.config import DEMO_DB_PATH
from litnav.goal import resolve_goal
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.cost import session_cost
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


def _trace_for(session_id: str) -> dict:
    """Build a trace from a live tutor's own per-session DB when present, else the demo DB."""
    ts = _TUTORS.get(session_id)
    if ts is not None:
        return build_trace(ts.conn, session_id)
    conn = _connect()
    try:
        return build_trace(conn, session_id)
    finally:
        conn.close()


def _list_sessions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, topic, status, created_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    return [{"id": r[0], "topic": r[1], "status": r[2], "created_at": r[3]} for r in rows]


@app.get("/sessions/{session_id}/trace")
def trace_json(session_id: str):
    return JSONResponse(_trace_for(session_id))


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_page(session_id: str):
    return _TEMPLATES.get_template("index.html").render(
        session_id=session_id, **_trace_for(session_id))


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

# Prefer the evidence-expanded fixture (Task 4) when present; else the curated 8-paper one.
_TUTOR_FIXTURE = ("data/seed/agents_expanded.json"
                  if Path("data/seed/agents_expanded.json").exists()
                  else "data/seed/agents_m3.json")


def _fixture_data() -> dict:
    return json.loads(Path(_TUTOR_FIXTURE).read_text(encoding="utf-8"))


def _n_papers(data: dict) -> int:
    if data.get("papers"):
        return len(data["papers"])
    ids = {c.get("paper_id") for c in data.get("chunks", []) if c.get("paper_id") is not None}
    return len(ids) or len(data["concepts"])


def _start_tutor(fixture: str, target_ids: list[int], pending_induction: dict | None) -> str:
    # Per-session DB + checkpoint files so concurrent tutors never clobber each other
    # or the CLI/panel demo DB (no shared-file deletion).
    sid = str(uuid.uuid4())
    base = Path(DEMO_DB_PATH).parent
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / f"tutor-{sid}.sqlite"), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, fixture)
    topic = json.loads(Path(fixture).read_text(encoding="utf-8"))["topic"]
    ckpt = sqlite3.connect(str(base / f"tutor-{sid}-ckpt.sqlite"), check_same_thread=False)
    ts = TutorSession(conn, ckpt, sid)
    ts.start(topic, target_concept_ids=target_ids, pending_induction=pending_induction,
             mastery_threshold=0.75)
    _TUTORS[sid] = ts
    return sid


@app.get("/tutor", response_class=HTMLResponse)
def tutor_home(message: str = ""):
    return _TEMPLATES.get_template("agent_home.html").render(
        message=message, n_papers=_n_papers(_fixture_data()))


@app.get("/tutor/start")
def tutor_start(goal: str = ""):
    data = _fixture_data()
    plan = resolve_goal(goal, data["concepts"], data["induction"]["off_skeleton"])
    if plan["kind"] == "concept":
        slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
        sid = _start_tutor(_TUTOR_FIXTURE, [slug_to_id[plan["slug"]]], None)
    elif plan["kind"] == "induce":
        sid = _start_tutor(_TUTOR_FIXTURE, [], data["induction"])
    else:
        avail = ", ".join(plan["available"])
        html = _TEMPLATES.get_template("agent_home.html").render(
            message=f'"{goal}" is not in this paper corpus. I can teach: {avail}.',
            n_papers=_n_papers(data))
        return HTMLResponse(html)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ts = _TUTORS.get(sid)
    if ts is None:
        return RedirectResponse("/tutor", status_code=303)
    return _TEMPLATES.get_template("agent.html").render(
        sid=sid, n_papers=_n_papers(_fixture_data()),
        cost=session_cost(ts.conn, sid), **ts.current())


@app.get("/tutor/{sid}/answer")
def tutor_answer(sid: str, answer: str = ""):
    ts = _TUTORS.get(sid)
    if ts is not None and answer.strip():
        ts.answer(answer)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn

    from litnav.config import load_dotenv
    load_dotenv()  # pick up LITNAV_LLM_* / OPENAI_API_KEY from .env
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
