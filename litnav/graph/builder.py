from __future__ import annotations

import re
import sqlite3
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from litnav.graph.router import tutor_router
from litnav.nodes.advance import advance_node
from litnav.nodes.check import check_node
from litnav.nodes.diagnose import diagnose_node
from litnav.nodes.grade import grade_node
from litnav.nodes.planner import planner_node
from litnav.nodes.replan import replan_node
from litnav.nodes.retrieve import retrieve_node
from litnav.nodes.select_next import route_after_select, select_next_node
from litnav.nodes.teach import teach_node
from litnav.state import NavState

# Module-level connection registry (single-threaded demo use)
_conn: sqlite3.Connection | None = None


def set_conn(conn: sqlite3.Connection) -> None:
    global _conn
    _conn = conn


def _get_conn() -> sqlite3.Connection:
    assert _conn is not None, "Call set_conn(conn) before invoking the graph"
    return _conn


# LangGraph node wrappers (capture conn from module-level registry)
def _planner(s: NavState) -> dict:      return planner_node(s, _get_conn())
def _select_next(s: NavState) -> dict:  return select_next_node(s)
def _retrieve(s: NavState) -> dict:     return retrieve_node(s, _get_conn())
def _teach(s: NavState) -> dict:        return teach_node(s, _get_conn())
def _check(s: NavState) -> dict:        return check_node(s, _get_conn())
def _grade(s: NavState) -> dict:        return grade_node(s, _get_conn())
def _diagnose(s: NavState) -> dict:     return diagnose_node(s, _get_conn())
def _replan(s: NavState) -> dict:       return replan_node(s, _get_conn())
def _advance(s: NavState) -> dict:      return advance_node(s, _get_conn())


def build_graph() -> object:
    workflow = StateGraph(NavState)

    workflow.add_node("planner", _planner)
    workflow.add_node("select_next", _select_next)
    workflow.add_node("retrieve", _retrieve)
    workflow.add_node("teach", _teach)
    workflow.add_node("check", _check)
    workflow.add_node("grade", _grade)
    workflow.add_node("diagnose", _diagnose)
    workflow.add_node("replan", _replan)
    workflow.add_node("advance", _advance)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "select_next")
    workflow.add_conditional_edges("select_next", route_after_select,
                                   {"retrieve": "retrieve", "__end__": END})
    workflow.add_edge("retrieve", "teach")
    workflow.add_edge("teach", "check")
    workflow.add_edge("check", "grade")
    workflow.add_conditional_edges("grade", tutor_router, {
        "advance": "advance",
        "diagnose": "diagnose",
        "reteach": "advance",   # M2 will replace
        "concede": "advance",   # M2 will replace
    })
    workflow.add_edge("diagnose", "replan")
    workflow.add_edge("replan", "select_next")
    workflow.add_edge("advance", "select_next")

    return workflow.compile(checkpointer=MemorySaver())


def make_initial_state(
    session_id: str,
    topic: str,
    target_concept_ids: list[int],
    pending_answers: list[str] | None = None,
    user_goal: str = "Learn the topic",
    mastery_threshold: float = 0.8,
) -> NavState:
    return {
        "session_id": session_id,
        "user_goal": user_goal,
        "topic": topic,
        "concept_dag": {},
        "all_concept_ids": [],
        "target_concept_ids": target_concept_ids,
        "route": [],
        "route_version": 1,
        "current_concept_id": None,
        "current_evidence": [],
        "current_quiz_item": None,
        "user_answer": None,
        "pending_answers": pending_answers or [],
        "quiz_result": None,
        "diagnosis": None,
        "decision": None,
        "rationale": None,
        "learner_state": {},
        "mastery_threshold": mastery_threshold,
        "reteach_count": {},
        "history": [],
    }


# ─── M0 compatibility shim (keep verify_m0 working) ─────────────────────────

_NEGATION_TOKENS = {"no", "not", "never", "isnt", "isn't", "arent", "aren't"}


def _normalize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


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
        if any(token in _NEGATION_TOKENS for token in prefix):
            continue
        return True
    return False


def _grade_answer(user_answer: str, answer_key: str) -> tuple[float, str]:
    correct = _matches_answer_key(user_answer, answer_key)
    score = 1.0 if correct else 0.0
    feedback = "Correct." if correct else f"Expected something like: {answer_key}"
    return score, feedback


def run_m0_session(
    conn: sqlite3.Connection,
    fixture_path: str = "data/seed/rag_demo.json",
    answer: str = "embedding vectors",
    session_id: str | None = None,
) -> str:
    import json
    from pathlib import Path

    from litnav.graph.router import tutor_router as _router
    from litnav.state import bkt_update, confidence_update, initial_concept_state
    from litnav.storage import repo

    if session_id is None:
        session_id = str(uuid.uuid4())

    data = json.loads(Path(fixture_path).read_text())
    topic = data["topic"]
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    target_ids = [slug_to_id[s] for s in data["targets"] if s in slug_to_id]

    repo.create_session(conn, session_id, topic)

    from litnav.nodes.planner import _build_dag, _topo_sort
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

    first_concept_id = route_order[0]
    first_step = steps[0]

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
    decision = _router(router_state)
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
