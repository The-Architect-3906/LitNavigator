"""M1 gate: python -m litnav.evaluation.verify_m1"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

from litnav.graph.builder import build_graph, make_initial_state
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
_BASE = Path("data/runtime")


def check(label: str, condition: bool) -> bool:
    if condition:
        print(f"G1 PASS: {label}")
    else:
        print(f"G1 FAIL: {label}", file=sys.stderr)
    return condition


def _setup(name: str) -> sqlite3.Connection:
    _BASE.mkdir(parents=True, exist_ok=True)
    db = _BASE / f"litnav-m1-{name}.sqlite"
    db.unlink(missing_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    return conn


def _fresh_ckpt(name: str) -> sqlite3.Connection:
    """Open a fresh file-backed checkpoint DB for this test slot."""
    ckpt_path = _BASE / f"litnav-m1-{name}-ckpt.sqlite"
    ckpt_path.unlink(missing_ok=True)
    return sqlite3.connect(str(ckpt_path), check_same_thread=False)


def _apply(state: dict, updates: dict) -> dict:
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def _run_concept(state: dict, conn: sqlite3.Connection, answer: str) -> dict:
    state = _apply(state, retrieve_node(state, conn))
    state = _apply(state, teach_node(state, conn))
    state = _apply(state, check_node(state, conn))
    state = {**state, "pending_answers": [answer]}
    updates = grade_node(state, conn)
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def main() -> int:
    data = json.loads(Path(FIXTURE).read_text())
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    dense_id = slug_to_id["dense_retrieval"]
    contrastive_id = slug_to_id["contrastive_learning"]

    results = []

    # ══════════════════════════════════════════════════════════════════════════
    # Node-level checks (verify routing logic in isolation)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Check 1: correct answer → advance ────────────────────────────────────
    conn_a = _setup("a")
    s = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id])
    s = _apply(s, planner_node(s, conn_a))
    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn_a, "embedding vectors")
    results.append(check("correct answer → tutor_router returns advance",
                          tutor_router(s) == "advance"))

    s = _apply(s, advance_node(s, conn_a))
    db_dec = conn_a.execute(
        "SELECT decision FROM decisions WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (s["session_id"],)
    ).fetchone()
    results.append(check("advance recorded in decisions table",
                          db_dec and db_dec[0] == "advance"))

    # ── Check 2: wrong answer + unmastered prereq → diagnose → replan ────────
    conn_b = _setup("b")
    s2 = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id, contrastive_id])
    s2 = _apply(s2, planner_node(s2, conn_b))

    s2 = _apply(s2, select_next_node(s2))
    s2 = _run_concept(s2, conn_b, "embedding vectors")
    s2 = _apply(s2, advance_node(s2, conn_b))

    s2 = _apply(s2, select_next_node(s2))
    results.append(check("select_next picks contrastive_learning after advance",
                          s2["current_concept_id"] == contrastive_id))

    s2 = _run_concept(s2, conn_b, "keyword matching")
    results.append(check("wrong answer → tutor_router returns diagnose",
                          tutor_router(s2) == "diagnose"))

    s2 = _apply(s2, diagnose_node(s2, conn_b))
    missing_id = s2["diagnosis"]["missing_concept_id"]
    results.append(check("missing prereq identified in diagnosis", missing_id is not None))

    old_version = s2["route_version"]
    s2 = _apply(s2, replan_node(s2, conn_b))
    results.append(check("route_version incremented by replan",
                          s2["route_version"] == old_version + 1))

    route_ids = [step["concept_id"] for step in s2["route"]]
    results.append(check("missing prereq inserted in route", missing_id in route_ids))

    prereq_pos = route_ids.index(missing_id)
    blocked_pos = route_ids.index(contrastive_id)
    results.append(check("prereq inserted before blocked concept", prereq_pos < blocked_pos))

    db_rat = conn_b.execute(
        "SELECT rationale FROM decisions WHERE session_id=? AND decision='replan'",
        (s2["session_id"],)
    ).fetchone()
    results.append(check("replan rationale is traceable in decisions table",
                          db_rat and len(db_rat[0]) > 10))

    db_ver = conn_b.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?",
        (s2["session_id"],)
    ).fetchone()[0]
    results.append(check("route_version in SQLite matches state",
                          db_ver == s2["route_version"]))

    # ══════════════════════════════════════════════════════════════════════════
    # Graph-level checks (real LangGraph app.invoke() paths)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Check 3: graph advance path (file-backed SqliteSaver) ────────────────
    conn_c = _setup("c")
    ckpt_c = _fresh_ckpt("c")
    app = build_graph(conn_c, checkpoint_conn=ckpt_c)
    sid_c = str(uuid.uuid4())
    s3 = make_initial_state(sid_c, data["topic"], [dense_id],
                             pending_answers=["embedding vectors"])
    app.invoke(s3, config={"configurable": {"thread_id": sid_c}, "recursion_limit": 50})

    dec_row = conn_c.execute(
        "SELECT decision FROM decisions WHERE session_id=? AND decision='advance'",
        (sid_c,)
    ).fetchone()
    results.append(check("graph invoke: advance path executed through LangGraph",
                          dec_row is not None))

    step_done = conn_c.execute(
        "SELECT status FROM route_steps WHERE session_id=? AND status='done'",
        (sid_c,)
    ).fetchone()
    results.append(check("graph invoke: route step marked done in SQLite",
                          step_done is not None))

    # ── Check 4: graph diagnose → replan path ────────────────────────────────
    conn_d = _setup("d")
    ckpt_d = _fresh_ckpt("d")
    app2 = build_graph(conn_d, checkpoint_conn=ckpt_d)
    sid_d = str(uuid.uuid4())
    s4 = make_initial_state(sid_d, data["topic"], [dense_id, contrastive_id],
                             pending_answers=["embedding vectors", "keyword matching"])
    app2.invoke(s4, config={"configurable": {"thread_id": sid_d}, "recursion_limit": 50})

    db_ver2 = conn_d.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?",
        (sid_d,)
    ).fetchone()[0]
    results.append(check("graph invoke: replan increments route_version via LangGraph",
                          db_ver2 is not None and db_ver2 >= 2))

    replan_dec = conn_d.execute(
        "SELECT id FROM decisions WHERE session_id=? AND decision='replan'",
        (sid_d,)
    ).fetchone()
    results.append(check("graph invoke: replan decision written via LangGraph",
                          replan_dec is not None))

    # ══════════════════════════════════════════════════════════════════════════
    # Checkpoint durability check (P2): interrupt → rebuild → resume
    # ══════════════════════════════════════════════════════════════════════════

    # ── Check 5: SqliteSaver checkpoint survives app rebuild ─────────────────
    conn_e = _setup("e")
    ckpt_path_e = _BASE / "litnav-m1-e-ckpt.sqlite"
    ckpt_path_e.unlink(missing_ok=True)

    sid_e = str(uuid.uuid4())
    s5 = make_initial_state(sid_e, data["topic"], [dense_id],
                             pending_answers=["embedding vectors"])

    # Phase 1: run graph, interrupt after grade node completes
    ckpt_conn_1 = sqlite3.connect(str(ckpt_path_e), check_same_thread=False)
    app_p1 = build_graph(conn_e, checkpoint_conn=ckpt_conn_1, interrupt_after=["grade"])
    app_p1.invoke(s5, config={"configurable": {"thread_id": sid_e}, "recursion_limit": 50})
    ckpt_conn_1.close()

    n_qa = conn_e.execute(
        "SELECT count(*) FROM quiz_attempts WHERE session_id=?", (sid_e,)
    ).fetchone()[0]
    results.append(check("checkpoint P1: grade executed — quiz_attempt written before interrupt",
                          n_qa == 1))

    n_adv_before = conn_e.execute(
        "SELECT count(*) FROM decisions WHERE session_id=? AND decision='advance'", (sid_e,)
    ).fetchone()[0]
    results.append(check("checkpoint P1: advance NOT written yet (graph interrupted before routing)",
                          n_adv_before == 0))

    # Phase 2: open a fresh connection to the same checkpoint file (simulates restart),
    #          then resume the suspended thread — graph continues from the conditional edge
    ckpt_conn_2 = sqlite3.connect(str(ckpt_path_e), check_same_thread=False)
    app_p2 = build_graph(conn_e, checkpoint_conn=ckpt_conn_2)
    app_p2.invoke(None, config={"configurable": {"thread_id": sid_e}, "recursion_limit": 50})
    ckpt_conn_2.close()

    n_adv_after = conn_e.execute(
        "SELECT count(*) FROM decisions WHERE session_id=? AND decision='advance'", (sid_e,)
    ).fetchone()[0]
    results.append(check("checkpoint P2: advance written after resume from rebuilt app instance",
                          n_adv_after >= 1))

    for c in (conn_a, conn_b, conn_c, conn_d, conn_e):
        c.close()

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
