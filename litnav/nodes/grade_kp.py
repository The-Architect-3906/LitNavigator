"""ASSESS phase grade node: semantic grading against rubric/expected_keypoints.

Replaces the exact-token-match grader for keypoint-level assessment.
Updates per-keypoint mastery and correct_obs; clears misconceptions on correct answers.

Escalation gate (spec §6.3 / §5):
  When the cheap grader returns low confidence AND the learner's mastery is near the
  mastery threshold (pedagogical-error-cost zone), re-grade once on the frontier model.
  Offline (provider=none) the fallback always has confidence=1.0 → never escalates.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import router
from litnav.state import BLOOM_LADDER, KP_CONF_THRESHOLD, KP_MASTERY_THRESHOLD, NavState, kp_bump, kp_confidence
from litnav.storage import repo

# Escalation constants
CONF_MIN = 0.6                                       # confidence below this triggers re-grade check
_BAND = (KP_MASTERY_THRESHOLD - 0.30, KP_MASTERY_THRESHOLD + 0.05)  # near-threshold mastery band
# NOTE: the A6 word-overlap "answer-relevance guard" was removed — it was English/Latin-only and
# force-failed CORRECT non-English answers (French/Spanish scored 0.0 vs English 1.0; live-test B7).
# Catching a rare off-topic answer was not worth systematically failing every non-English learner;
# the LLM grader handles genuine off-topic answers. (Off-topic SOURCE matching stays in discover.)


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

    # Resolve current mastery BEFORE the LLM call (needed for escalation band check)
    kps = dict(cp["keypoint_state"])
    s = dict(kps.get(kp_id, {}))
    old_mastery = s.get("mastery", 0.3)

    fallback_correct = bool(
        answer.strip() and quiz.get("answer_key", "").lower() in answer.lower()
    )
    language = state.get("target_language") or "English"

    # Grade for the KEY IDEA (paraphrases ok), not verbatim / over-strict rubric matching.
    # GEPA-tuned: the old "grade strictly" prompt rejected correct paraphrases on EVERY model (incl.
    # gpt-5.4 / gpt-5.5 — stronger models were *stricter*); the key-idea prompt scores 100% on the
    # eval at cheap gpt-4o-mini. confidence + score_0_5 stay for the frontier escalation gate below.
    grade_prompt = (
        "You are grading a learner's short answer. Judge ONLY whether it conveys the expected "
        "key idea, the way a fair human tutor would.\n"
        "Rules: (1) accept paraphrases, synonyms, and correct partial answers that still capture "
        "the key idea; (2) mark WRONG if it omits the key idea, gives only a fragment of a required "
        "set, is too vague to evaluate, or states a misconception; (3) ignore style, length, and "
        f"extra detail. Write the \"feedback\" field in {language}. Return JSON only.\n"
        f"Question: {quiz.get('question', '')}\n"
        f"Expected key idea: {quiz.get('answer_key', '')}\n"
        f"Supporting evidence: {evidence}\n"
        f"Learner's answer: {answer!r}\n"
        '{"correct": bool, '
        '"feedback": "1-2 sentences for the learner, grounded in the evidence: name WHY it is right or '
        'wrong (the key idea), and if wrong or partial give a specific hint toward the correct idea", '
        '"confidence": 0.0-1.0, "score_0_5": 0-5, '
        '"misconception_resolved": ["list of misconception ids cleared, or empty"]}'
    )
    fallback_base = {
        "correct": fallback_correct,
        "feedback": "Correct." if fallback_correct else f"Expected: {quiz.get('answer_key', '')}",
        "confidence": 1.0,   # offline fallback is always "certain" → never escalates
        "score_0_5": 5 if fallback_correct else 0,
        "misconception_resolved": [],
    }
    verdict = router.complete_json(
        grade_prompt,
        tier="cheap",
        stage="grade",
        fallback=fallback_base,
        session_id=state["session_id"],
        conn=conn,
    )

    # ── Escalation gate (spec §6.3 / §5) ──────────────────────────────────────
    # Escalate ONLY when cheap grader is uncertain AND mastery is in the near-threshold
    # band where a wrong correctness call has high pedagogical cost.
    conf = float(verdict.get("confidence", 1.0))
    near = _BAND[0] <= old_mastery <= _BAND[1]
    escalated = False
    if conf < CONF_MIN and near:
        verdict = router.complete_json(
            grade_prompt,
            tier="frontier",
            stage="grade_escalate",
            fallback=verdict,          # use cheap verdict as frontier fallback (offline safe)
            session_id=state["session_id"],
            conn=conn,
        )
        escalated = True
    # ──────────────────────────────────────────────────────────────────────────

    correct = bool(verdict.get("correct"))
    feedback = verdict.get("feedback") or ("Correct." if correct else "Try again.")

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
            "mastery_before": old_mastery,
            **({"escalated": True} if escalated else {}),
        },
        "rationale": (
            f"GRADE {bloom} on '{kp_id}': {'correct' if correct else 'wrong'} "
            f"(mastery {old_mastery:.2f}→{s['mastery']:.2f}, "
            f"correct_obs={s.get('correct_obs', 0)}"
            + (", escalated=True" if escalated else "")
            + ")"
        ),
        "history": [{
            "event": "grade_kp",
            "keypoint_id": kp_id,
            "bloom": bloom,
            "correct": correct,
            "mastery": s["mastery"],
            "quiz_id": quiz.get("id"),   # needed by assess_next de-dup
            **({"escalated": True} if escalated else {}),
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
        # Respect the goal's Bloom CEILING (survey→comprehension, functional/mastery→application).
        # Without this, a survey goal keeps trying to upgrade past its ceiling: assess_next caps the
        # bloom, re-poses the same question, and the concept NEVER advances — an infinite re-quiz loop
        # (found by the inner-loop storyboard capture on a survey-goal scenario).
        ceiling = state.get("bloom_ceiling") or BLOOM_LADDER[-1]
        ceil_idx = BLOOM_LADDER.index(ceiling) if ceiling in BLOOM_LADDER else len(BLOOM_LADDER) - 1
        if idx + 1 < len(BLOOM_LADDER) and idx < ceil_idx:
            return "assess_next"   # upgrade bloom on same keypoint (still below the ceiling)
        # At the Bloom ceiling (or ladder top) with a correct answer → concept-level mastery check.
        # 'hold' = not yet mastered → keep quizzing at the ceiling (each correct raises mastery until
        # the threshold is met); it does NOT escalate Bloom past the ceiling anymore.
        dec = route_decider_node(state)
        return {"advance": "advance_kp", "replan": "diagnose", "hold": "assess_next"}[dec]

    # Wrong answer
    if s.get("reteach_count", 0) < 2:
        return "reteach_kp"

    # Exhausted reteaches — check for an unmastered prereq to detour through first.
    # The `p not in in_route` guard prevents infinite loops: replan inserts the prereq
    # once; on the next exhaustion it's already in-route and we fall through to concede.
    dag = state.get("concept_dag") or {}
    ls = state.get("learner_state") or {}
    thr = state.get("mastery_threshold", 0.75)
    in_route = {s["concept_id"] for s in state.get("route", [])}
    prereqs = dag.get(cp["concept_id"], [])
    unmastered = [p for p in prereqs if ls.get(p, {}).get("mastery", 0.0) < thr and p not in in_route]
    if unmastered:
        return "diagnose"   # detour: insert the missing prerequisite first

    # No prereq detour available → check thresholds; 'hold' means concede and move on
    dec = route_decider_node(state)
    return {"advance": "advance_kp", "hold": "advance_kp"}[dec]
