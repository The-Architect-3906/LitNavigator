"""ASSESS phase grade node: semantic grading against rubric/expected_keypoints.

Replaces the exact-token-match grader for keypoint-level assessment.
Updates per-keypoint mastery and correct_obs; clears misconceptions on correct answers.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.state import BLOOM_LADDER, KP_CONF_THRESHOLD, KP_MASTERY_THRESHOLD, NavState, kp_bump, kp_confidence
from litnav.storage import repo


def grade_kp_node(state: NavState, conn: sqlite3.Connection) -> dict:
    cp = state["concept_progress"]
    quiz = state.get("current_quiz_item") or {}
    kp_id = cp["current_keypoint_id"]
    answer = (state.get("pending_answers") or [None])[0] or state.get("user_answer") or ""

    pending = list(state.get("pending_answers") or [])
    if pending:
        pending.pop(0)

    evidence = repo.get_chunk_text(conn, quiz.get("evidence_chunk_id") or "")
    rubric = quiz.get("rubric") or f"Key idea: {quiz.get('answer_key', '')}"
    expected = quiz.get("expected_keypoints") or quiz.get("answer_key") or ""
    bloom = cp["current_bloom"] or "recall"

    fallback_correct = bool(
        answer.strip() and quiz.get("answer_key", "").lower() in answer.lower()
    )
    verdict = llm_client.complete_json(
        f"Grade this answer strictly against the rubric. Return JSON only.\n"
        f"Question: {quiz.get('question', '')}\n"
        f"Rubric: {rubric}\n"
        f"Expected key ideas: {expected}\n"
        f"Evidence from paper: {evidence}\n"
        f"Learner's answer: {answer!r}\n"
        '{"correct": bool, "feedback": "one sentence", '
        '"misconception_resolved": ["list of misconception ids cleared, or empty"]}',
        fallback={
            "correct": fallback_correct,
            "feedback": "Correct." if fallback_correct else f"Expected: {quiz.get('answer_key', '')}",
            "misconception_resolved": [],
        },
    )

    correct = bool(verdict.get("correct"))
    feedback = verdict.get("feedback") or ("Correct." if correct else "Try again.")

    kps = dict(cp["keypoint_state"])
    s = dict(kps.get(kp_id, {}))
    old_mastery = s.get("mastery", 0.3)
    s["mastery"] = kp_bump(old_mastery, bloom, correct)
    s["last_result"] = "correct" if correct else "wrong"
    if correct:
        s["correct_obs"] = s.get("correct_obs", 0) + 1

    misconceptions = dict(cp.get("misconceptions", {}))
    if correct:
        for mid in (verdict.get("misconception_resolved") or []):
            misconceptions[mid] = False
    elif quiz.get("targets_misconception"):
        misconceptions.setdefault(quiz["targets_misconception"], True)

    kps[kp_id] = s
    updated_cp = {**cp, "keypoint_state": kps, "misconceptions": misconceptions}

    repo.record_quiz_attempt(
        conn, state["session_id"], quiz.get("id") or 0, answer,
        1.0 if correct else 0.0, feedback,
        concept_score_delta={"mastery_delta": round(s["mastery"] - old_mastery, 4)},
        detected_misconception=quiz.get("targets_misconception") if not correct else None,
    )

    reteach_count = cp["keypoint_state"].get(kp_id, {}).get("reteach_count", 0)
    turn_type = "reteach" if reteach_count > 0 else "teach"
    repo.record_tutor_turn(
        conn, state["session_id"], cp["concept_id"], turn_type,
        cp.get("current_bloom") or "recall",
        pre_check_score=None,
        post_check_score=1.0 if correct else 0.0,
        cited_chunks=list(state.get("current_cited_chunks") or []),
        token_cost=0,
        mastery_after=s["mastery"],
        confidence_after=kp_confidence(s.get("correct_obs", 0)),
    )

    return {
        "concept_progress": updated_cp,
        "pending_answers": pending,
        "user_answer": None,
        "quiz_result": {
            "score": 1.0 if correct else 0.0,
            "feedback": feedback,
            "answer": answer,
            "keypoint_id": kp_id,
            "bloom": bloom,
            "mastery": s["mastery"],
        },
        "rationale": (
            f"GRADE {bloom} on '{kp_id}': {'correct' if correct else 'wrong'} "
            f"(mastery {old_mastery:.2f}→{s['mastery']:.2f}, correct_obs={s['correct_obs']})"
        ),
        "history": [{
            "event": "grade_kp",
            "keypoint_id": kp_id,
            "bloom": bloom,
            "correct": correct,
            "mastery": s["mastery"],
        }],
    }


def assess_decider(state: NavState) -> str:
    """Route after grade_kp: upgrade bloom / reteach keypoint / advance or replan.

    Returns one of: assess_next | reteach_kp | advance_kp | diagnose
    route_decider logic is inlined here so advance_kp only runs on true mastery.
    """
    from litnav.nodes.route_decider import route_decider_node
    cp = state["concept_progress"]
    kp_id = cp["current_keypoint_id"]
    s = cp["keypoint_state"].get(kp_id, {})
    bloom = cp["current_bloom"] or "recall"

    if s.get("last_result") == "correct":
        idx = BLOOM_LADDER.index(bloom)
        if idx + 1 < len(BLOOM_LADDER):
            return "assess_next"   # upgrade bloom on same keypoint
        # Hit top of ladder (application) with a correct answer → concept-level check
        dec = route_decider_node(state)
        return {"advance": "advance_kp", "replan": "diagnose", "hold": "assess_next"}[dec]

    # Wrong answer
    if s.get("reteach_count", 0) < 2:
        return "reteach_kp"

    # Exhausted reteaches → concept-level route decision
    dec = route_decider_node(state)
    return {"advance": "advance_kp", "replan": "diagnose", "hold": "assess_next"}[dec]
