from __future__ import annotations

import sqlite3
import re
import uuid

from litnav.graph.router import tutor_router
from litnav.retrieval.fake import retrieve_evidence
from litnav.state import bkt_update, confidence_update, initial_concept_state
from litnav.storage import repo

NEGATION_TOKENS = {"no", "not", "never", "isnt", "isn't", "arent", "aren't"}


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


def _grade_answer(user_answer: str, answer_key: str) -> tuple[float, str]:
    correct = _matches_answer_key(user_answer, answer_key)
    score = 1.0 if correct else 0.0
    feedback = "Correct." if correct else f"Expected something like: {answer_key}"
    return score, feedback


def _matches_answer_key(user_answer: str, answer_key: str) -> bool:
    answer_tokens = _normalize_tokens(user_answer)
    key_tokens = _normalize_tokens(answer_key)
    if not answer_tokens or not key_tokens or len(answer_tokens) < len(key_tokens):
        return False

    window = len(key_tokens)
    for start in range(len(answer_tokens) - window + 1):
        if answer_tokens[start : start + window] != key_tokens:
            continue
        prefix = answer_tokens[max(0, start - 3) : start]
        if any(token in NEGATION_TOKENS for token in prefix):
            continue
        return True

    return False


def _normalize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def run_m0_session(
    conn: sqlite3.Connection,
    fixture_path: str = "data/seed/rag_demo.json",
    answer: str = "embedding vectors",
    session_id: str | None = None,
) -> str:
    import json
    from pathlib import Path

    if session_id is None:
        session_id = str(uuid.uuid4())

    data = json.loads(Path(fixture_path).read_text())
    topic = data["topic"]
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    target_ids = [slug_to_id[s] for s in data["targets"] if s in slug_to_id]

    repo.create_session(conn, session_id, topic)

    dag = _build_dag(conn)
    route_order = _topo_sort(target_ids, dag)

    learner_state: dict[int, dict] = {}
    for c in data["concepts"]:
        learner_state[c["id"]] = initial_concept_state()
        repo.upsert_learner_state(
            conn, session_id, c["id"],
            mastery=0.4, confidence=0.0, n_observations=0,
        )

    route_version = 1
    steps = [
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
    repo.write_route_steps(conn, session_id, route_version, steps)

    # teach and quiz the first concept (dense_retrieval) with the provided answer
    first_concept_id = route_order[0]
    first_step = steps[0]

    evidence = retrieve_evidence(conn, first_concept_id)

    quiz = repo.get_quiz_item(conn, first_concept_id)
    score, feedback = _grade_answer(answer, quiz["answer_key"])

    cs = learner_state[first_concept_id]
    new_mastery = bkt_update(cs["mastery"], correct=(score == 1.0), taught=True)
    new_n = cs["n_observations"] + 1
    new_confidence = confidence_update(new_n)
    learner_state[first_concept_id].update(
        mastery=new_mastery, confidence=new_confidence, n_observations=new_n
    )

    repo.upsert_learner_state(
        conn, session_id, first_concept_id,
        mastery=new_mastery, confidence=new_confidence, n_observations=new_n,
    )

    delta = {"mastery_delta": round(new_mastery - 0.4, 4)}
    repo.record_quiz_attempt(
        conn, session_id, quiz["id"], answer, score, feedback,
        concept_score_delta=delta,
    )

    router_state = {
        "current_concept_id": first_concept_id,
        "mastery_threshold": 0.8,
        "learner_state": learner_state,
        "concept_dag": dag,
        "reteach_count": {},
    }
    decision = tutor_router(router_state)
    rationale = (
        f"Quiz score={score:.1f}. Mastery updated to {new_mastery:.3f}. Router decided: {decision}."
    )

    repo.record_decision(
        conn, session_id, route_version, "tutor_router", decision, rationale,
        state_snapshot={"concept_id": first_concept_id, "mastery": new_mastery},
    )

    new_status = "done" if decision == "advance" else "active"
    repo.update_route_step_status(conn, session_id, route_version, first_step["step_id"], new_status)

    return session_id
