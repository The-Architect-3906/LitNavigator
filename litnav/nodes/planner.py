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
    """Topological order with full transitive prerequisite expansion.

    Previously this guarded with `if prereq in target_ids`, which silently dropped
    any prereq not explicitly requested. Now we expand to the full transitive closure
    so that asking for a downstream concept automatically queues its prereq chain.
    """
    # 1. Collect the full transitive closure (target + all ancestors)
    full_set: set[int] = set()

    def _collect(cid: int) -> None:
        if cid in full_set:
            return
        full_set.add(cid)
        for prereq in dag.get(cid, []):
            _collect(prereq)

    for cid in target_ids:
        _collect(cid)

    # 2. Standard DFS topological sort over the expanded set
    visited: set[int] = set()
    order: list[int] = []

    def _visit(cid: int) -> None:
        if cid in visited:
            return
        visited.add(cid)
        for prereq in dag.get(cid, []):
            if prereq in full_set:
                _visit(prereq)
        order.append(cid)

    for cid in sorted(full_set):
        _visit(cid)
    return order


def _topo_sort_priority(target_ids: list[int], dag: dict[int, list[int]],
                        priority: dict[int, int]) -> list[int]:
    """Topological order (prereqs first) that, among available concepts, prefers lower
    priority rank (ties broken by id). Used for intent frontier-first ordering.

    Like _topo_sort, expands the full transitive closure first so that prereqs not
    explicitly listed in target_ids are still included."""
    import heapq

    # Expand to full transitive closure (same as _topo_sort)
    full_set: set[int] = set()

    def _collect(cid: int) -> None:
        if cid in full_set:
            return
        full_set.add(cid)
        for prereq in dag.get(cid, []):
            _collect(prereq)

    for cid in target_ids:
        _collect(cid)

    # Assign lower priority to implicitly-added prereqs (they have no frontier flag)
    full_priority = {cid: priority.get(cid, 1) for cid in full_set}

    indeg = {t: 0 for t in full_set}
    adj: dict[int, list[int]] = {t: [] for t in full_set}
    for t in full_set:
        for p in dag.get(t, []):
            if p in full_set:
                indeg[t] += 1
                adj[p].append(t)
    avail = [(full_priority.get(t, 1), t) for t in full_set if indeg[t] == 0]
    heapq.heapify(avail)
    order: list[int] = []
    while avail:
        _, t = heapq.heappop(avail)
        order.append(t)
        for d in adj[t]:
            indeg[d] -= 1
            if indeg[d] == 0:
                heapq.heappush(avail, (full_priority.get(d, 1), d))
    return order


def planner_node(state: NavState, conn: sqlite3.Connection) -> dict:
    from litnav.intent import resolve as resolve_intent

    session_id = state["session_id"]
    topic = state["topic"]

    repo.create_session(conn, session_id, topic)

    dag = _build_dag(conn)

    # Intent mode re-scopes the targets (and, for journalist, leads with the live debate).
    intent_cfg = resolve_intent(state.get("intent"))
    if intent_cfg:
        slug_to_id = {row[0]: row[1] for row in conn.execute("SELECT slug, id FROM concepts")}
        target_ids = [slug_to_id[s] for s in intent_cfg["targets"] if s in slug_to_id]
    else:
        target_ids = state["target_concept_ids"]

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

    if intent_cfg and intent_cfg.get("frontier_first"):
        frontier = {r[0]: r[1] for r in conn.execute("SELECT id, frontier_flag FROM concepts")}
        rank = {cid: (0 if frontier.get(cid) in ("contested", "open") else 1) for cid in target_ids}
        route_order = _topo_sort_priority(list(target_ids), dag, rank)
    else:
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
