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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from litnav.config import DEMO_DB_PATH
from litnav.goal import resolve_goal
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.cost import session_cost
from litnav.ui.interactive import AgentSession, TutorSession
from litnav.ui.trace import build_trace

# In-memory live tutor sessions (single-process demo). Keyed by session id.
_TUTORS: dict[str, TutorSession] = {}
_AGENTS: dict[str, AgentSession] = {}

app = FastAPI(title="LitNavigator trace panel")

_TEMPLATES = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _connect() -> sqlite3.Connection:
    # Default to the demo DB the CLI runner populates; honor an explicit override.
    return sqlite3.connect(os.getenv("LITNAV_DB_PATH", DEMO_DB_PATH))


def _trace_for(session_id: str) -> dict:
    """Build a trace from a live session's own per-session DB when present, else the demo DB."""
    ag = _AGENTS.get(session_id)
    if ag is not None:
        return build_trace(ag.conn, session_id)
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


def _story_context(data: dict) -> dict:
    papers = data.get("papers") or []
    concepts = data.get("concepts") or []
    edges = data.get("edges") or []
    topic = data.get("topic", "LLM-based autonomous agents")

    preferred_arxiv = [
        "2210.03629",  # ReAct
        "2302.04761",  # Toolformer
        "2303.11366",  # Reflexion
        "2308.00352",  # MetaGPT
        "2308.11432",  # Survey
    ]
    by_arxiv = {p.get("arxiv_id"): p for p in papers}
    reps = [by_arxiv[a] for a in preferred_arxiv if a in by_arxiv]
    if len(reps) < 5:
        seen = {p.get("id") for p in reps}
        reps.extend([p for p in papers if p.get("id") not in seen][: 5 - len(reps)])

    slug_to_name = {c["slug"]: c["name"] for c in concepts if c.get("slug")}
    target_names = [slug_to_name[s] for s in data.get("targets", []) if s in slug_to_name]
    concept_names = [c["name"] for c in concepts]

    return {
        "story_domain": topic,
        "story_paper_count": _n_papers(data),
        "story_representative_papers": reps,
        "story_concept_count": len(concepts),
        "story_edge_count": len(edges),
        "story_target_names": target_names,
        "story_concept_names": concept_names,
    }


def _start_agent(goal: str, intent: str | None) -> str:
    sid = str(uuid.uuid4())
    base = Path(DEMO_DB_PATH).parent
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / f"tutor-{sid}.sqlite"), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, _TUTOR_FIXTURE)
    ckpt = sqlite3.connect(str(base / f"tutor-{sid}-ckpt.sqlite"), check_same_thread=False)
    ag = AgentSession(conn, ckpt, sid, _fixture_data())
    _AGENTS[sid] = ag
    # An intent (researcher/journalist) starts teaching immediately; an explicit teachable
    # goal also starts teaching; anything else stays in conversation until the user says more.
    if intent:
        ag.tutor = TutorSession(conn, ckpt, sid)
        ag.tutor.start(ag.topic, target_concept_ids=[], intent=intent, mastery_threshold=0.75)
    else:
        plan = resolve_goal(goal, ag.concepts, ag.off)
        if plan["kind"] in ("concept", "induce"):
            list(ag._start_teaching(plan["slug"]))   # run the first teach now
    return sid


@app.get("/tutor", response_class=HTMLResponse)
def tutor_home(message: str = ""):
    data = _fixture_data()
    return _TEMPLATES.get_template("agent_home.html").render(
        message=message, n_papers=_n_papers(data), **_story_context(data))


@app.get("/tutor/start")
def tutor_start(goal: str = "", intent: str = ""):
    from litnav.intent import INTENTS
    sid = _start_agent(goal, intent if intent in INTENTS else None)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ag = _AGENTS.get(sid)
    if ag is None:
        return RedirectResponse("/tutor", status_code=303)
    data = _fixture_data()
    return _TEMPLATES.get_template("agent.html").render(
        sid=sid, n_papers=_n_papers(data),
        cost=session_cost(ag.conn, sid), **_story_context(data), **ag.current())


@app.post("/tutor/{sid}/events")
async def tutor_events(sid: str, request: Request):
    # POST (answer in the JSON body, not the URL) so learner answers don't leak into
    # request logs / browser history and long answers don't hit URL limits. The client
    # consumes the SSE stream via fetch() + ReadableStream (EventSource is GET-only).
    ag = _AGENTS.get(sid)
    if ag is None:
        return JSONResponse({"type": "error", "message": "no such session"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("answer") or "").strip()

    def gen():
        try:
            stream = ag.handle(message) if message else iter(ag.current_events())
            for ev in stream:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn

    from litnav.config import load_dotenv
    load_dotenv()  # pick up LITNAV_LLM_* / OPENAI_API_KEY from .env
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
