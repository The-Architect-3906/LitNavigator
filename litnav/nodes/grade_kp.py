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
    bloom = cp["current_bloom"] or "recall"

    fallback_correct = bool(
        answer.strip() and quiz.get("answer_key", "").lower() in answer.lower()
    )
    # Grade for the KEY IDEA (paraphrases ok), not verbatim / over-strict rubric matching.
    # GEPA-tuned: the old "grade strictly" prompt rejected correct paraphrases on EVERY model
    # (incl. gpt-5.4 / gpt-5.5 — stronger models were *stricter*); this key-idea prompt scores
    # 100% on the grading eval at cheap gpt-4o-mini. The model was never the problem; the prompt was.
    verdict = llm_client.complete_json(
        "You are grading a learner's short answer. Judge ONLY whether it conveys the expected "
        "key idea, the way a fair human tutor would.\n"
        "Rules: (1) accept paraphrases, synonyms, and correct partial answers that still capture "
        "the key idea; (2) mark WRONG if it omits the key idea, gives only a fragment of a required "
        "set, is too vague to evaluate, or states a misconception; (3) ignore style, length, and "
        "extra detail. Return JSON only.\n"
        f"Question: {quiz.get('question', '')}\n"
        f"Expected key idea: {quiz.get('answer_key', '')}\n"
        f"Supporting evidence: {evidence}\n"
        f"Learner's answer: {answer!r}\n"
        '{"correct": bool, "feedback": "one short sentence for the learner", '
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

    # Misconception detection: the keypoint path previously only echoed the quiz's static
    # `targets_misconception` (usually unset → nothing ever surfaced). Detect from the ANSWER
    # against the concept's misconception bank, like the legacy grade path does.
    from litnav.nodes.grade import _detect_misconception
    detected_mid = None
    misconceptions = dict(cp.get("misconceptions", {}))
    if correct:
        for mid in (verdict.get("misconception_resolved") or []):
            misconceptions[mid] = False
    else:
        candidates = repo.get_misconceptions_for_concept(conn, cp["concept_id"])
        detected_mid = _detect_misconception(answer, candidates) or quiz.get("targets_misconception")
        if detected_mid:
            misconceptions.setdefault(detected_mid, True)

    kps[kp_id] = s
    updated_cp = {**cp, "keypoint_state": kps, "misconceptions": misconceptions}

    # Persist concept-level mastery to learner_state so the glass-box learner model actually
    # moves (previously keypoint mastery lived only in graph state → bars stayed flat at 0.4).
    concept_mastery = round(sum(k.get("mastery", 0.3) for k in kps.values()) / max(len(kps), 1), 3)
    total_obs = sum(k.get("correct_obs", 0) for k in kps.values())
    held = [mid for mid, active in misconceptions.items() if active]
    repo.upsert_learner_state(
        conn, state["session_id"], cp["concept_id"],
        mastery=concept_mastery, confidence=kp_confidence(total_obs),
        n_observations=total_obs, held_misconceptions=held, depth=bloom,
    )
    # Mirror into GRAPH-STATE learner_state too (legacy grade.py does this): the live agent page + SSE
    # learner bars read this dict via current(); writing only the DB left them flat (caught by G-live-tutor).
    learner_state = dict(state.get("learner_state") or {})
    learner_state[cp["concept_id"]] = {
        **learner_state.get(cp["concept_id"], {}),
        "mastery": concept_mastery, "confidence": kp_confidence(total_obs),
        "n_observations": total_obs, "held_misconceptions": held, "depth": bloom,
    }

    repo.record_quiz_attempt(
        conn, state["session_id"], quiz.get("id") or 0, answer,
        1.0 if correct else 0.0, feedback,
        concept_score_delta={"mastery_delta": round(s["mastery"] - old_mastery, 4)},
        detected_misconception=detected_mid,
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
        "learner_state": learner_state,
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
            "quiz_id": quiz.get("id"),   # needed by assess_next de-dup
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

    # Exhausted reteaches → check thresholds; 'hold' means concede and move on
    dec = route_decider_node(state)
    return {"advance": "advance_kp", "hold": "advance_kp"}[dec]
