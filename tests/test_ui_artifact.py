"""Artifact generation + download tests for the web UI — offline/$0.

A curated (offline) session is driven to completion; we assert an `artifact` terminal event is
emitted, the .md file exists, and the download endpoint serves it as an attachment.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Keep these tests offline/$0; restored after each test (no global pollution)."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")


def _drive_to_done(tutor, max_turns: int = 80) -> dict:
    """Drive the compiled tutor graph to END, mirroring the proven harness driver:
    answer each posed quiz with its real answer_key; when paused without a quiz, resume."""
    app, config = tutor.app, tutor.config
    for _ in range(max_turns):
        snap = app.get_state(config)
        if not snap.next:            # reached END
            break
        quiz = snap.values.get("current_quiz_item")
        if not quiz:
            app.invoke(None, config)
            continue
        ak = quiz.get("answer_key") or ""
        app.update_state(config, {"pending_answers": [ak], "user_answer": ak, "user_intent": None})
        app.invoke(None, config)
    return tutor.current()


def _curated_session(tmp_path) -> AgentSession:
    conn = sqlite3.connect(":memory:"); init_db(conn)
    seed_demo_data(conn, "data/seed/agents_expanded.json")
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    data = json.loads(Path("data/seed/agents_expanded.json").read_text(encoding="utf-8"))
    ag = AgentSession(conn, ck, "sa", data, out_dir=str(tmp_path))
    slug = data["concepts"][0]["slug"]
    list(ag._start_teaching(slug))
    return ag


def test_artifact_event_and_file(tmp_path):
    ag = _curated_session(tmp_path)
    cur = _drive_to_done(ag.tutor)
    assert cur.get("done"), "session did not reach a terminal state"
    evs = ag.tutor._terminal_events()
    art = [e for e in evs if e.get("type") == "artifact"]
    assert art, "expected an artifact event at session end"
    assert art[0]["url"] == "/tutor/sa/artifact"
    assert Path(ag.tutor.artifact_path).exists()
    # generated exactly once
    again = [e for e in ag.tutor._terminal_events() if e.get("type") == "artifact"]
    assert not again, "artifact should be generated only once"


def test_artifact_download_route(tmp_path, monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from fastapi.testclient import TestClient
    from litnav.ui import server
    monkeypatch.setattr(server, "_ARTIFACT_DIR", str(tmp_path))
    c = TestClient(server.app)

    loc = c.get("/tutor/start", params={"goal": "ReAct"}, follow_redirects=False).headers["location"]
    sid = loc.split("/tutor/")[1]
    ag = server._AGENTS[sid]

    _drive_to_done(ag.tutor)                       # complete the session
    c.post(f"/tutor/{sid}/events", json={})        # stream terminal events → generates the artifact

    resp = c.get(f"/tutor/{sid}/artifact")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 0
