"""M1 gate: python -m litnav.evaluation.verify_m1

Asserts the M1 adaptive-routing guarantee as it stands after the ORIENT→TEACH→ASSESS
refactor: the planner expands the FULL transitive prerequisite closure up front, so a
prerequisite of a target is taught PROACTIVELY (front-loaded into the route, before its
dependent) rather than inserted REACTIVELY after a wrong answer. The reactive
diagnose→replan path still exists in code and is exercised by the induce/off-skeleton
flow (see verify_m3); it no longer fires for in-corpus prerequisites, which are
front-loaded, so M1 no longer asserts it.
"""
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
from litnav.nodes.grade import grade_node
from litnav.nodes.planner import planner_node
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
    data = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    dense_id = slug_to_id["dense_retrieval"]
    contrastive_id = slug_to_id["contrastive_learning"]
    neg_id = slug_to_id["negative_sampling"]   # prerequisite of contrastive_learning, NOT a target

    results = []

    # ══════════════════════════════════════════════════════════════════════════
    # Node-level checks (verify routing logic in isolation)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Check 1: correct answer -> advance ────────────────────────────────────
    conn_a = _setup("a")
    s = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id])
    s = _apply(s, planner_node(s, conn_a))
    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn_a, "embedding vectors")
    results.append(check("correct answer -> tutor_router returns advance",
                          tutor_router(s) == "advance"))

    s = _apply(s, advance_node(s, conn_a))
    db_dec = conn_a.execute(
        "SELECT decision FROM decisions WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (s["session_id"],)
    ).fetchone()
    results.append(check("advance recorded in decisions table",
                          db_dec and db_dec[0] == "advance"))

    # ── Check 2: planner front-loads the full prerequisite closure (proactive M1) ──
    # negative_sampling is a prerequisite of contrastive_learning but is NOT a target. The
    # planner expands the full transitive prerequisite closure, so negative_sampling appears
    # in the route ahead of contrastive_learning — the learner meets the prerequisite
    # proactively, not after stumbling on the dependent.
    conn_b = _setup("b")
    s2 = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id, contrastive_id])
    s2 = _apply(s2, planner_node(s2, conn_b))
    route_ids = [step["concept_id"] for step in s2["route"]]
    results.append(check("planner front-loads the prerequisite (negative_sampling) into the route",
                          neg_id in route_ids))
    results.append(check("prerequisite ordered before its dependent (contrastive_learning)",
                          neg_id in route_ids and contrastive_id in route_ids
                          and route_ids.index(neg_id) < route_ids.index(contrastive_id)))

    # select_next walks prereqs-first: after advancing the first concept, the next concept
    # picked is the front-loaded prerequisite, not the final target.
    s2 = _apply(s2, select_next_node(s2))
    s2 = _run_concept(s2, conn_b, "embedding vectors")          # dense_retrieval (correct)
    s2 = _apply(s2, advance_node(s2, conn_b))
    s2 = _apply(s2, select_next_node(s2))
    results.append(check("select_next walks the front-loaded prereq before the target",
                          s2["current_concept_id"] == neg_id))

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

    # ── Check 4: graph teaches the full prereq closure, prerequisite before dependent ──
    conn_d = _setup("d")
    ckpt_d = _fresh_ckpt("d")
    app2 = build_graph(conn_d, checkpoint_conn=ckpt_d)
    sid_d = str(uuid.uuid4())
    s4 = make_initial_state(sid_d, data["topic"], [dense_id, contrastive_id],
                             pending_answers=["embedding vectors", "non-relevant alternatives",
                                              "they are pulled together"])
    app2.invoke(s4, config={"configurable": {"thread_id": sid_d}, "recursion_limit": 100})

    teach_order = [r[0] for r in conn_d.execute(
        "SELECT concept_id FROM tutor_turns WHERE session_id=? ORDER BY id", (sid_d,)
    ).fetchall()]
    results.append(check("graph invoke: prerequisite taught before its dependent",
                          neg_id in teach_order and contrastive_id in teach_order
                          and teach_order.index(neg_id) < teach_order.index(contrastive_id)))

    n_done = conn_d.execute(
        "SELECT count(*) FROM route_steps WHERE session_id=? AND status='done'", (sid_d,)
    ).fetchone()[0]
    results.append(check("graph invoke: all route steps reach done on correct answers (3/3)",
                          n_done == 3))

    # ══════════════════════════════════════════════════════════════════════════
    # Checkpoint durability check (P2): interrupt -> rebuild -> resume
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
    results.append(check("checkpoint P1: grade executed -> quiz_attempt written before interrupt",
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
