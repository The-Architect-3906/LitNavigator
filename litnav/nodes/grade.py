from __future__ import annotations

import re
import sqlite3

from litnav.grading import grade_answer
from litnav.llm import client as llm_client
from litnav.state import NavState, bkt_update, confidence_update
from litnav.storage import repo


def _detect_misconception(answer: str, candidates: list[dict]) -> str | None:
    """Deterministic detection: first misconception whose detect_hint regex matches the answer."""
    for m in candidates:
        hint = m.get("detect_hint")
        if hint and re.search(hint, answer, flags=re.IGNORECASE):
            return m["id"]
    return None


def grade_node(state: NavState, conn: sqlite3.Connection) -> dict:
    session_id = state["session_id"]
    concept_id = state["current_concept_id"]
    quiz_item = state.get("current_quiz_item")

    pending = list(state.get("pending_answers") or [])
    answer = pending.pop(0) if pending else (state.get("user_answer") or "")

    if quiz_item is None:
        return {
            "pending_answers": pending,
            "user_answer": None,
            "quiz_result": {"score": 0.0, "feedback": "No quiz item found.", "answer": answer},
        }

    score, feedback = grade_answer(answer, quiz_item["answer_key"])
    correct = score == 1.0

    # ── Misconception detection (only meaningful on a wrong answer) ──────────────
    detected_id = None
    # Start from the teach turn's LLM cost (grounded explanation), then add grading's own cost.
    turn_token_cost = int(state.get("teach_token_cost") or 0)
    candidates = repo.get_misconceptions_for_concept(conn, concept_id)
    if not correct and candidates:
        deterministic = _detect_misconception(answer, candidates)
        # LLM seam: with provider=qwen the LLM picks the misconception id; the deterministic
        # result is the offline fallback so this stays correct with provider=none.
        prompt = (
            "A learner answered a quiz about a concept. Pick which misconception their answer "
            "reveals, or null if none.\n"
            f"Answer: {answer!r}\n"
            f"Candidate misconceptions: {[{'id': m['id'], 'wrong_model': m['wrong_model']} for m in candidates]}\n"
            'Respond as JSON: {"misconception_id": "<id or null>"}'
        )
        result = llm_client.complete_json(prompt, fallback={"misconception_id": deterministic})
        turn_token_cost += llm_client.last_token_cost()  # 0 offline; real token usage when a provider is set
        # Only trust an id the model could legitimately have chosen; otherwise fall back to the
        # deterministic detection. Guards against a malformed/unknown id from a live LLM polluting
        # held_misconceptions / quiz_attempts and breaking reteach's anchor to the correct model.
        candidate_ids = {m["id"] for m in candidates}
        llm_id = result.get("misconception_id")
        detected_id = llm_id if llm_id in candidate_ids else deterministic

    # ── Learner state update ────────────────────────────────────────────────────
    learner_state = dict(state["learner_state"])
    cs = dict(learner_state.get(concept_id, {}))
    old_mastery = cs.get("mastery", 0.4)
    n_obs = cs.get("n_observations", 0) + 1
    new_mastery = bkt_update(old_mastery, correct=correct, taught=True)
    new_confidence = confidence_update(n_obs)

    held = list(cs.get("held_misconceptions", []))
    if correct:
        held = []  # mastered the point → drop held misconceptions for this concept
    elif detected_id and detected_id not in held:
        held.append(detected_id)

    # Record the strategy used this turn (T3: two distinct strategies across teach+reteach).
    tried = list(cs.get("tried_strategies", []))
    strategy = state.get("current_strategy") or "direct"
    if strategy not in tried:
        tried.append(strategy)

    cs.update(mastery=new_mastery, confidence=new_confidence, n_observations=n_obs,
              held_misconceptions=held, tried_strategies=tried)
    learner_state[concept_id] = cs

    repo.upsert_learner_state(
        conn, session_id, concept_id,
        mastery=new_mastery, confidence=new_confidence, n_observations=n_obs,
        held_misconceptions=held, tried_strategies=tried,
    )

    delta = {"mastery_delta": round(new_mastery - old_mastery, 4)}
    repo.record_quiz_attempt(
        conn, session_id, quiz_item["id"], answer, score, feedback,
        concept_score_delta=delta, detected_misconception=detected_id,
    )

    # ── Tutor turn (T5 learning gain: reteach post > prior teach post) ──────────
    reteach_count = state.get("reteach_count", {}).get(concept_id, 0)
    turn_type = "reteach" if reteach_count > 0 else "teach"
    pre_score = repo.get_last_tutor_post_score(conn, session_id, concept_id)
    repo.record_tutor_turn(
        conn, session_id, concept_id, turn_type, strategy,
        pre_check_score=pre_score, post_check_score=score,
        cited_chunks=state.get("current_cited_chunks") or [],
        token_cost=turn_token_cost,
        mastery_after=new_mastery, confidence_after=new_confidence,
    )

    quiz_result = {
        "score": score, "feedback": feedback, "answer": answer,
        "mastery": new_mastery, "confidence": new_confidence, "concept_id": concept_id,
        "detected_misconception": detected_id,
    }

    return {
        "learner_state": learner_state,
        "quiz_result": quiz_result,
        "pending_answers": pending,
        "user_answer": None,
        "history": [{"event": "grade", "concept_id": concept_id, "score": score,
                     "mastery": new_mastery, "detected_misconception": detected_id}],
    }
