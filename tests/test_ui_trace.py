import json
import os
import sqlite3
import uuid

from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui import server
from litnav.ui.trace import build_trace

FIXTURE = "data/seed/agents_m2.json"


def _seed_reteach_session(db_path: str) -> str:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    ckpt = sqlite3.connect(db_path + ".ckpt", check_same_thread=False)
    app = build_graph(conn, ckpt)
    sid = str(uuid.uuid4())
    state = make_initial_state(
        sid, "LLM-based autonomous agents", [1],
        pending_answers=["it just uses chain of thought", "the agent takes actions and observations"],
        mastery_threshold=0.75,
    )
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    conn.commit()
    conn.close()
    return sid


def test_build_trace_has_core_sections(tmp_path):
    db = tmp_path / "ui.sqlite"
    sid = _seed_reteach_session(str(db))
    conn = sqlite3.connect(str(db))
    trace = build_trace(conn, sid)
    assert trace["route"], "route present"
    assert trace["decisions"], "decisions present"
    assert trace["evidence"], "cited evidence present"
    assert trace["tutor_turns"], "tutor turns present"
    assert any(d["decision"] == "reteach" for d in trace["decisions"])


def test_trace_endpoint_returns_json(tmp_path):
    db = tmp_path / "ui2.sqlite"
    sid = _seed_reteach_session(str(db))
    os.environ["LITNAV_DB_PATH"] = str(db)
    try:
        resp = server.trace_json(sid)
        data = json.loads(bytes(resp.body))
        assert data["route"] and data["decisions"] and data["evidence"]
        html = server.session_page(sid)
        assert "route_version" in html and "ReAct" in html
    finally:
        del os.environ["LITNAV_DB_PATH"]


def test_story_context_exposes_offline_discover_digest_artifacts():
    data = server._fixture_data()
    story = server._story_context(data)
    assert story["story_domain"]
    assert story["story_paper_count"] >= 5
    assert len(story["story_representative_papers"]) == 5
    assert story["story_concept_count"] >= 3
    assert story["story_concept_names"]
