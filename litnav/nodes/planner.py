from __future__ import annotations

import sqlite3
import uuid

from litnav.state import NavState, initial_concept_state
from litnav.storage import repo


def _build_dag(conn: sqlite3.Connection) -> dict[int, list[int]]:
    rows = conn.execute(
        "SELECT target_concept, prereq_concept FROM concept_edges WHERE edge_type='prerequisite'"
    ).fetchall()
    dag: dict[int, list[int]] = {}
    for target, prereq in rows:
        dag.setdefault(target, []).append(prereq)
    return dag


def _topo_sort(target_ids: list[int], dag: dict[int, list[int]]) -> list[int]:
    visited: set[int] = set()
    order: list[int] = []

    def visit(cid: int) -> None:
        if cid in visited:
            return
        visited.add(cid)
        for prereq in dag.get(cid, []):
            if prereq in target_ids:
                visit(prereq)
        order.append(cid)

    for cid in sorted(target_ids):
        visit(cid)
    return order


def planner_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    target_ids = state["target_concept_ids"]
    topic = state["topic"]

    repo.create_session(conn, session_id, topic)

    dag = _build_dag(conn)

    all_rows = conn.execute("SELECT id FROM concepts").fetchall()
    all_ids = [r[0] for r in all_rows]

    learner_state = {}
    for cid in all_ids:
        cs = initial_concept_state()
        learner_state[cid] = cs
        repo.upsert_learner_state(conn, session_id, cid, **{
            "mastery": cs["mastery"],
            "confidence": cs["confidence"],
            "n_observations": cs["n_observations"],
        })

    route_order = _topo_sort(list(target_ids), dag)
    route = [
        {
            "step_id": f"route-{i+1:03d}",
            "concept_id": cid,
            "paper_id": None,
            "reason": "Initial route from concept DAG.",
            "status": "pending",
            "confidence": 1.0,
        }
        for i, cid in enumerate(route_order)
    ]
    repo.write_route_steps(conn, session_id, 1, route)

    return {
        "concept_dag": dag,
        "all_concept_ids": all_ids,
        "learner_state": learner_state,
        "route": route,
        "route_version": 1,
        "history": [{"event": "planner", "route": [s["concept_id"] for s in route]}],
    }
