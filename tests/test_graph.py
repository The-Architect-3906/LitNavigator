import sqlite3
import uuid

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.graph_svg import to_svg
from litnav.ui.trace import build_trace, concept_graph

FIXTURE = "data/seed/agents_m3.json"


def _conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    return conn


def test_base_graph_has_all_concepts_and_curated_edges():
    g = concept_graph(_conn(), session_id=None)
    assert len(g["nodes"]) == 7
    assert len(g["edges"]) == 6  # react->{2,3,4,6,7}, reflection->5
    assert all(n["state"] == "idle" and not n["induced"] for n in g["nodes"])
    assert all(e["source"] == "curated" for e in g["edges"])


def test_to_svg_renders_without_dependency():
    svg = to_svg(concept_graph(_conn(), None))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "ReAct" in svg  # a node label made it in


def test_session_graph_marks_current_and_conceded():
    from litnav.graph.builder import build_graph, make_initial_state
    conn = _conn()
    sid = str(uuid.uuid4())
    react_id = 1
    app = build_graph(conn, sqlite3.connect(":memory:", check_same_thread=False))
    # One wrong answer with no recognized misconception -> concede.
    state = make_initial_state(sid, "agents", [react_id],
                               pending_answers=["totally unrelated"], mastery_threshold=0.75)
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})

    g = concept_graph(conn, sid)
    react = next(n for n in g["nodes"] if n["id"] == react_id)
    assert react["state"] == "conceded"


def test_glassbox_meaningful_at_first_pause_then_fills():
    """The advisor's concern: build_trace must return usable data on a paused live session,
    and grow each turn. Drive a TutorSession to its first post-check pause, then one answer."""
    from litnav.ui.interactive import TutorSession
    conn = _conn()
    sid = str(uuid.uuid4())
    ts = TutorSession(conn, sqlite3.connect(":memory:", check_same_thread=False), sid)
    ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)

    # At the first pause: route + concepts are already persisted; no decision yet.
    t0 = build_trace(conn, sid)
    assert t0["route"], "route written before the first pause"
    assert t0["concepts"], "learner_state seeded before the first pause"
    assert t0["timeline"] == []

    ts.answer("actions and observations from the environment")
    t1 = build_trace(conn, sid)
    assert t1["timeline"], "a graded turn appears after the first answer"
    assert t1["decisions"], "a routing decision is recorded after the first answer"
