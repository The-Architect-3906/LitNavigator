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

from fastapi import FastAPI, Query, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, RedirectResponse,
                               StreamingResponse)
from jinja2 import Environment, FileSystemLoader, select_autoescape

from litnav.config import DEMO_DB_PATH
from litnav.goal import resolve_goal
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession, TutorSession
from litnav.ui.trace import build_trace

# In-memory live tutor sessions (single-process demo). Keyed by session id.
_TUTORS: dict[str, TutorSession] = {}
_AGENTS: dict[str, AgentSession] = {}

# Where session take-away artifacts are written (one subdir per session).
_ARTIFACT_DIR = "artifacts"

app = FastAPI(title="LitNavigator trace panel")

_TEMPLATES = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _connect() -> sqlite3.Connection:
    # Default to the demo DB the CLI runner populates; honor an explicit override.
    conn = sqlite3.connect(os.getenv("LITNAV_DB_PATH", DEMO_DB_PATH))
    init_db(conn)  # idempotent: guarantees the schema so index/panel reads can't 500 on an empty DB
    return conn


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


def _live_story_context(ag) -> dict:
    """Build the story-band context from a live open-world session's real DB data.

    Returns the same keys as _story_context so agent.html renders unchanged.
    Queries ag.conn (the per-session SQLite that digest already populated).
    """
    conn = ag.conn
    concepts = conn.execute("SELECT name FROM concepts ORDER BY id").fetchall()
    concept_names = [r[0] for r in concepts]

    papers = conn.execute("SELECT title, year FROM papers ORDER BY id").fetchall()
    paper_count = len(papers)
    rep_papers = [{"title": r[0], "year": r[1] or ""} for r in papers[:5]]

    try:
        edge_count = conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0]
    except Exception:
        edge_count = 0

    return {
        "story_domain": ag.goal or ag.topic,
        "story_paper_count": paper_count,
        "story_representative_papers": rep_papers,
        "story_concept_count": len(concept_names),
        "story_edge_count": edge_count,
        "story_target_names": concept_names[:4],
        "story_concept_names": concept_names,
    }


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


def _start_agent(goal: str, intent: str | None, selected_adapters: list[str] | None = None) -> str:
    sid = str(uuid.uuid4())
    base = Path(DEMO_DB_PATH).parent
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / f"tutor-{sid}.sqlite"), check_same_thread=False)
    init_db(conn)
    ckpt = sqlite3.connect(str(base / f"tutor-{sid}-ckpt.sqlite"), check_same_thread=False)

    live = os.getenv("LITNAV_LLM_PROVIDER", "none") != "none"
    if live and goal.strip() and not intent:
        # OPEN-WORLD: build this learner's own concept graph from real sources. No fixture.
        # The page auto-streams the cold start (discover → digest → teach) on first /events.
        repo.create_session(conn, sid, topic=goal.strip())
        _AGENTS[sid] = AgentSession(conn, ckpt, sid, fixture_data=None,
                                    open_world_goal=goal.strip(), live=True, out_dir=_ARTIFACT_DIR,
                                    selected_adapters=selected_adapters)
        return sid

    # CURATED offline pack (deterministic, $0) — unchanged behaviour.
    seed_demo_data(conn, _TUTOR_FIXTURE)
    ag = AgentSession(conn, ckpt, sid, _fixture_data(), out_dir=_ARTIFACT_DIR)
    _AGENTS[sid] = ag
    # An intent (researcher/journalist) starts teaching immediately; an explicit teachable
    # goal also starts teaching; anything else stays in conversation until the user says more.
    if intent:
        ag.tutor = TutorSession(conn, ckpt, sid, out_dir=_ARTIFACT_DIR)
        ag.tutor.start(ag.topic, target_concept_ids=[], intent=intent, mastery_threshold=0.75)
    else:
        plan = resolve_goal(goal, ag.concepts, ag.off)
        if plan["kind"] in ("concept", "induce"):
            list(ag._start_teaching(plan["slug"]))   # run the first teach now
    return sid


# ── Scenario display metadata (name + emoji) keyed by slug ──────────────────
_SCENARIO_DISPLAY: dict[str, tuple[str, str]] = {
    "diffusion-models":        ("Diffusion Models",          "🎨"),
    "crispr":                  ("CRISPR Gene Editing",       "🧬"),
    "raft-consensus":          ("Raft Consensus",             "🗳️"),
    "quantum-error-correction":("Quantum Error Correction",  "⚛️"),
    "black-scholes":           ("Black-Scholes Options Pricing", "📈"),
    "mrna-vaccines":           ("mRNA Vaccines",             "💉"),
    "transformer-attention":   ("Transformer Self-Attention","🔤"),
    "behavioral-economics":    ("Behavioral Economics",      "🧠"),
    "rlhf":                    ("RLHF",                      "🤖"),
    "graph-neural-nets":       ("Graph Neural Networks",     "🕸️"),
}

# Full language name map for two-letter codes → human-readable label
_LANG_NAMES: dict[str, str] = {
    "English": "English", "Chinese": "中文", "Spanish": "Español", "French": "Français",
}


def _enrich_scenarios(scenarios: list[dict]) -> list[dict]:
    """Return a new list of scenario dicts with 'name', 'emoji', 'lang_label' added."""
    out = []
    for s in scenarios:
        name, emoji = _SCENARIO_DISPLAY.get(s["slug"], (s["slug"].replace("-", " ").title(), "📖"))
        out.append({**s, "name": name, "emoji": emoji,
                    "lang_label": _LANG_NAMES.get(s["language"], s["language"])})
    return out


@app.get("/tutor", response_class=HTMLResponse)
def tutor_home(message: str = ""):
    from litnav.discover.adapters import available_adapters
    from litnav.evaluation.e2e_scenarios import SCENARIOS
    data = _fixture_data()
    live = os.getenv("LITNAV_LLM_PROVIDER", "none") != "none"
    return _TEMPLATES.get_template("agent_home.html").render(
        message=message, n_papers=_n_papers(data), adapters=available_adapters(),
        live=live, scenarios=_enrich_scenarios(SCENARIOS), **_story_context(data))


@app.get("/tutor/start")
def tutor_start(goal: str = "", intent: str = "", adapters: list[str] = Query(default=[])):
    from litnav.intent import INTENTS
    sid = _start_agent(goal, intent if intent in INTENTS else None, selected_adapters=adapters or None)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ag = _AGENTS.get(sid)
    if ag is None:
        return RedirectResponse("/tutor", status_code=303)
    artifact_url = (f"/tutor/{sid}/artifact"
                    if getattr(getattr(ag, "tutor", None), "artifact_path", None) else None)
    # Live open-world sessions: story band from the session's REAL sources/concepts (bug fix);
    # curated/offline sessions keep the fixture story. cost is in ag.current() (B6 symmetric paint).
    if ag.open_world:
        story = _live_story_context(ag)
        n_papers = story["story_paper_count"]
    else:
        data = _fixture_data()
        story = _story_context(data)
        n_papers = _n_papers(data)
    return _TEMPLATES.get_template("agent.html").render(
        sid=sid, n_papers=n_papers, artifact_url=artifact_url,
        live=ag.open_world, **story, **ag.current())


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
    if not isinstance(body, dict):
        body = {}
    # str() so a non-string answer (number/list/bool) can't crash .strip() with a 500.
    message = str(body.get("answer") or "").strip()

    def gen():
        try:
            stream = ag.handle(message) if message else iter(ag.current_events())
            for ev in stream:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/tutor/{sid}/artifact")
def tutor_artifact(sid: str):
    """Download the session's take-away artifact (Markdown). Generated at session end."""
    ag = _AGENTS.get(sid)
    path = getattr(getattr(ag, "tutor", None), "artifact_path", None) if ag else None
    if not path or not Path(path).exists():
        return JSONResponse({"error": "no artifact yet — finish the session first"}, status_code=404)
    fname = f"litnavigator-{sid[:8]}-{Path(path).stem}.md"
    return FileResponse(path, media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn

    from litnav.config import load_dotenv
    load_dotenv()  # pick up LITNAV_LLM_* / OPENAI_API_KEY from .env
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
