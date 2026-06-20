import sqlite3
import uuid

import pytest

from litnav.graph.builder import make_initial_state
from litnav.graph.router import tutor_router
from litnav.nodes.advance import advance_node
from litnav.nodes.check import check_node
from litnav.nodes.diagnose import diagnose_node
from litnav.nodes.grade import grade_node
from litnav.nodes.planner import planner_node
from litnav.nodes.replan import replan_node
from litnav.nodes.retrieve import retrieve_node
from litnav.nodes.select_next import select_next_node
from litnav.nodes.teach import teach_node
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/rag_demo.json"


def _setup(tmp_path):
    conn = sqlite3.connect(tmp_path / "litnav.sqlite")
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    return conn


def _apply(state, updates):
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def _run_concept(state, conn, answer):
    state = _apply(state, retrieve_node(state, conn))
    state = _apply(state, teach_node(state, conn))
    state = _apply(state, check_node(state, conn))
    state = {**state, "pending_answers": [answer]}
    updates = grade_node(state, conn)
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def _slug_to_id(conn):
    rows = conn.execute("SELECT slug, id FROM concepts").fetchall()
    return {r[0]: r[1] for r in rows}


def test_correct_answer_advances(tmp_path):
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", [ids["dense_retrieval"]])
    s = _apply(s, planner_node(s, conn))
    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn, "embedding vectors")
    assert tutor_router(s) == "advance"


def test_wrong_answer_stays_below_threshold(tmp_path):
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", [ids["dense_retrieval"]])
    s = _apply(s, planner_node(s, conn))
    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn, "keyword matching")
    mastery = s["learner_state"][ids["dense_retrieval"]]["mastery"]
    assert mastery < 0.8


def test_expanded_route_covers_prereq_gap(tmp_path):
    """topo-sort now expands the full prereq closure upfront.
    targets [dense_retrieval, contrastive_learning] auto-includes negative_sampling."""
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    targets = [ids["dense_retrieval"], ids["contrastive_learning"]]
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", targets)
    out = planner_node(s, conn)
    route_ids = [step["concept_id"] for step in out["route"]]

    assert ids["negative_sampling"] in route_ids, "prereq must be auto-included in route"
    neg_pos = route_ids.index(ids["negative_sampling"])
    cl_pos = route_ids.index(ids["contrastive_learning"])
    assert neg_pos < cl_pos, "prereq must appear before its dependent"


def test_prereq_already_in_route_replan_noop(tmp_path):
    """When the prereq is already in the expanded route, replan_noop runs:
    version still increments (as an event record) and the prereq stays in the route."""
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    targets = [ids["dense_retrieval"], ids["contrastive_learning"]]
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", targets)
    s = _apply(s, planner_node(s, conn))

    # Force current_concept_id to contrastive_learning so diagnose can find negative_sampling
    # as an unmastered prereq (mastery defaults to 0 → below 0.8 threshold).
    s2 = {**s, "current_concept_id": ids["contrastive_learning"]}
    old_version = s2["route_version"]
    s2 = _apply(s2, diagnose_node(s2, conn))
    missing_id = s2["diagnosis"]["missing_concept_id"]

    # negative_sampling is unmastered AND already in the expanded route
    assert missing_id == ids["negative_sampling"]
    s2 = _apply(s2, replan_node(s2, conn))

    # replan_noop still increments the version as an event record
    assert s2["route_version"] == old_version + 1
    route_ids = [step["concept_id"] for step in s2["route"]]
    assert missing_id in route_ids  # already in route — no duplicate insertion


def test_replan_rationale_in_db(tmp_path):
    """replan_noop (prereq already in route) records a rationale row in the decisions table."""
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    targets = [ids["dense_retrieval"], ids["contrastive_learning"]]
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", targets)
    s = _apply(s, planner_node(s, conn))

    # Force diagnose+replan_noop on contrastive_learning (prereq already in expanded route)
    s2 = {**s, "current_concept_id": ids["contrastive_learning"]}
    s2 = _apply(s2, diagnose_node(s2, conn))
    s2 = _apply(s2, replan_node(s2, conn))

    row = conn.execute(
        "SELECT rationale FROM decisions WHERE session_id=? AND decision='replan_noop'",
        (s2["session_id"],),
    ).fetchone()
    assert row is not None
    assert len(row[0]) > 10


def test_route_version_in_db_matches_state(tmp_path):
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    targets = [ids["dense_retrieval"], ids["contrastive_learning"]]
    s = make_initial_state(str(uuid.uuid4()), "RAG for scientific QA", targets)
    s = _apply(s, planner_node(s, conn))

    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn, "embedding vectors")
    s = _apply(s, advance_node(s, conn))

    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn, "keyword matching")
    s = _apply(s, diagnose_node(s, conn))
    s = _apply(s, replan_node(s, conn))

    db_version = conn.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?",
        (s["session_id"],),
    ).fetchone()[0]
    assert db_version == s["route_version"]


def _mem_ckpt():
    return sqlite3.connect(":memory:", check_same_thread=False)


def test_graph_compiles(tmp_path):
    from litnav.graph.builder import build_graph
    conn = _setup(tmp_path)
    app = build_graph(conn, checkpoint_conn=_mem_ckpt())
    assert app is not None


def test_graph_advance_via_invoke(tmp_path):
    from litnav.graph.builder import build_graph, make_initial_state
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    app = build_graph(conn, checkpoint_conn=_mem_ckpt())
    sid = str(uuid.uuid4())
    state = make_initial_state(sid, "RAG for scientific QA", [ids["dense_retrieval"]],
                               pending_answers=["embedding vectors"])
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    row = conn.execute(
        "SELECT decision FROM decisions WHERE session_id=? AND decision='advance'", (sid,)
    ).fetchone()
    assert row is not None


def test_graph_prereq_route_via_invoke(tmp_path):
    """Expanded route [dense_retrieval, negative_sampling, contrastive_learning] runs
    end-to-end without replan: topo-sort ensures the prereq is always present upfront."""
    from litnav.graph.builder import build_graph, make_initial_state
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    app = build_graph(conn, checkpoint_conn=_mem_ckpt())
    sid = str(uuid.uuid4())
    state = make_initial_state(
        sid, "RAG for scientific QA",
        [ids["dense_retrieval"], ids["contrastive_learning"]],
        pending_answers=["embedding vectors", "keyword matching", "keyword matching"],
    )
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    ver = conn.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?", (sid,)
    ).fetchone()[0]
    # No replan needed: prereq is already in the expanded route, so route_version stays at 1
    assert ver == 1


def test_checkpoint_durability(tmp_path):
    """Interrupt after grade, rebuild app from same file checkpoint, resume → advance written."""
    from litnav.graph.builder import build_graph, make_initial_state
    conn = _setup(tmp_path)
    ids = _slug_to_id(conn)
    ckpt_path = tmp_path / "ckpt.sqlite"
    sid = str(uuid.uuid4())
    state = make_initial_state(sid, "RAG for scientific QA", [ids["dense_retrieval"]],
                               pending_answers=["embedding vectors"])

    # Phase 1: run with interrupt after grade
    ckpt1 = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    app1 = build_graph(conn, checkpoint_conn=ckpt1, interrupt_after=["grade"])
    app1.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    ckpt1.close()

    # grade ran — quiz_attempt written; advance node has NOT run yet
    assert conn.execute(
        "SELECT count(*) FROM quiz_attempts WHERE session_id=?", (sid,)
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT count(*) FROM decisions WHERE session_id=? AND decision='advance'", (sid,)
    ).fetchone()[0] == 0

    # Phase 2: new connection to same file (simulates process restart), resume
    ckpt2 = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    app2 = build_graph(conn, checkpoint_conn=ckpt2)
    app2.invoke(None, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    ckpt2.close()

    assert conn.execute(
        "SELECT count(*) FROM decisions WHERE session_id=? AND decision='advance'", (sid,)
    ).fetchone()[0] >= 1
