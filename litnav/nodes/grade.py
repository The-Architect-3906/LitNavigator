from __future__ import annotations

import sqlite3

from litnav.grading import grade_answer
from litnav.state import NavState, bkt_update, confidence_update
from litnav.storage import repo


def grade_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    quiz_item = state.get("current_quiz_item")

    # Get answer: pop from pending_answers queue (batch/gate mode) or use user_answer
    pending = list(state.get("pending_answers") or [])
    if pending:
        answer = pending.pop(0)
    else:
        answer = state.get("user_answer") or ""

    if quiz_item is None:
        return {
            "pending_answers": pending,
            "user_answer": None,
            "quiz_result": {"score": 0.0, "feedback": "No quiz item found.", "answer": answer},
        }

    score, feedback = grade_answer(answer, quiz_item["answer_key"])

    learner_state = dict(state["learner_state"])
    cs = dict(learner_state.get(concept_id, {}))
    old_mastery = cs.get("mastery", 0.4)
    n_obs = cs.get("n_observations", 0) + 1
    new_mastery = bkt_update(old_mastery, correct=(score == 1.0), taught=True)
    new_confidence = confidence_update(n_obs)

    cs.update(mastery=new_mastery, confidence=new_confidence, n_observations=n_obs)
    learner_state[concept_id] = cs

    repo.upsert_learner_state(
        conn, session_id, concept_id,
        mastery=new_mastery, confidence=new_confidence, n_observations=n_obs,
    )

    delta = {"mastery_delta": round(new_mastery - old_mastery, 4)}
    repo.record_quiz_attempt(
        conn, session_id, quiz_item["id"], answer, score, feedback,
        concept_score_delta=delta,
    )

    quiz_result = {"score": score, "feedback": feedback, "answer": answer,
                   "mastery": new_mastery, "concept_id": concept_id}

    return {
        "learner_state": learner_state,
        "quiz_result": quiz_result,
        "pending_answers": pending,
        "user_answer": None,
        "history": [{"event": "grade", "concept_id": concept_id,
                     "score": score, "mastery": new_mastery}],
    }
