"""M1 gate: python -m litnav.evaluation.verify_m1"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

from litnav.graph.builder import make_initial_state, set_conn
from litnav.nodes.advance import advance_node
from litnav.nodes.check import check_node
from litnav.nodes.diagnose import diagnose_node
from litnav.nodes.grade import grade_node
from litnav.nodes.planner import planner_node
from litnav.nodes.replan import replan_node
from litnav.nodes.retrieve import retrieve_node
from litnav.nodes.select_next import select_next_node
from litnav.nodes.teach import teach_node
from litnav.graph.router import tutor_router
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

DB_PATH = Path("data/runtime/litnav-m1.sqlite")
FIXTURE = "data/seed/rag_demo.json"


def check(label: str, condition: bool) -> bool:
    if condition:
        print(f"G1 PASS: {label}")
    else:
        print(f"G1 FAIL: {label}", file=sys.stderr)
    return condition


def _setup(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    set_conn(conn)
    return conn


def _run_concept(state: dict, conn: sqlite3.Connection, answer: str) -> dict:
    """Run one full teach→check→grade cycle with a given answer."""
    state = {**state, **retrieve_node(state, conn)}
    state = {**state, **teach_node(state, conn)}
    state = {**state, **check_node(state, conn)}
    state = {**state, "pending_answers": [answer]}
    updates = grade_node(state, conn)
    # merge history
    hist = state.get("history", []) + updates.pop("history", [])
    state = {**state, **updates, "history": hist}
    return state


def _apply(state: dict, updates: dict) -> dict:
    hist = state.get("history", []) + updates.pop("history", [])
    return {**state, **updates, "history": hist}


def main() -> int:
    results = []

    # ── Test 1: correct answer advances ──────────────────────────────────────
    conn = _setup(DB_PATH.with_suffix(".a.sqlite"))
    import json
    from pathlib import Path as P
    data = json.loads(P(FIXTURE).read_text())
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    target_ids = [slug_to_id[s] for s in data["targets"] if s in slug_to_id]
    # Use only dense_retrieval (id=1) to keep it simple
    dense_id = slug_to_id["dense_retrieval"]

    s = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id])
    s = _apply(s, planner_node(s, conn))
    s = _apply(s, select_next_node(s))
    s = _run_concept(s, conn, answer="embedding vectors")

    decision = tutor_router(s)
    results.append(check("correct answer advances", decision == "advance"))

    s = _apply(s, advance_node(s, conn))
    db_dec = conn.execute(
        "SELECT decision FROM decisions WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (s["session_id"],)
    ).fetchone()
    results.append(check("advance recorded in decisions", db_dec and db_dec[0] == "advance"))

    # ── Test 2: wrong answer → prereq diagnosed → replan ─────────────────────
    conn2 = _setup(DB_PATH.with_suffix(".b.sqlite"))
    # Use dense_retrieval + contrastive_learning (has prereq negative_sampling)
    contrastive_id = slug_to_id["contrastive_learning"]
    s2 = make_initial_state(str(uuid.uuid4()), data["topic"], [dense_id, contrastive_id])
    s2 = _apply(s2, planner_node(s2, conn2))

    # Advance through dense_retrieval (correct answer)
    s2 = _apply(s2, select_next_node(s2))
    s2 = _run_concept(s2, conn2, answer="embedding vectors")
    s2 = _apply(s2, advance_node(s2, conn2))

    # Now on contrastive_learning — answer wrong
    s2 = _apply(s2, select_next_node(s2))
    results.append(check("select_next picks contrastive_learning",
                          s2["current_concept_id"] == contrastive_id))

    s2 = _run_concept(s2, conn2, answer="keyword matching")  # wrong
    decision2 = tutor_router(s2)
    results.append(check("prerequisite failure diagnosed", decision2 == "diagnose"))

    s2 = _apply(s2, diagnose_node(s2, conn2))
    missing_id = s2["diagnosis"]["missing_concept_id"]
    results.append(check("missing prereq identified", missing_id is not None))

    old_version = s2["route_version"]
    s2 = _apply(s2, replan_node(s2, conn2))
    results.append(check("route_version incremented", s2["route_version"] == old_version + 1))

    route_concept_ids = [step["concept_id"] for step in s2["route"]]
    results.append(check("missing prereq inserted in route", missing_id in route_concept_ids))

    # Verify prereq is inserted BEFORE contrastive_learning
    prereq_pos = route_concept_ids.index(missing_id)
    blocked_pos = route_concept_ids.index(contrastive_id)
    results.append(check("prereq inserted before blocked concept", prereq_pos < blocked_pos))

    # Verify rationale is traceable
    db_rationale = conn2.execute(
        "SELECT rationale FROM decisions WHERE session_id=? AND decision='replan'",
        (s2["session_id"],)
    ).fetchone()
    results.append(check("rationale traceable in decisions table",
                          db_rationale and len(db_rationale[0]) > 10))

    # Verify route_version in DB
    db_version = conn2.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?",
        (s2["session_id"],)
    ).fetchone()[0]
    results.append(check("route_version in SQLite matches state",
                          db_version == s2["route_version"]))

    conn.close()
    conn2.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
