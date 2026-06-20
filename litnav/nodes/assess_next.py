"""ASSESS phase: select and pose the next quiz item.

Quiz source: get_or_generate — hits cache (quiz_items table) first;
generates via LLM with evidence grounding only on a cache miss.
Demo core concepts should have their questions pre-generated offline
so the live demo never depends on a live LLM call for question generation.
"""
from __future__ import annotations

import json
import sqlite3

from litnav.assess import quizgen
from litnav.llm import router
from litnav.state import BLOOM_LADDER, NavState
from litnav.storage import repo


def _get_or_generate(
    conn: sqlite3.Connection,
    concept_id: int,
    keypoint_id: str,
    bloom: str,
    used_ids: list[int],
    session_id: str | None = None,
) -> dict | None:
    """Cache-first quiz retrieval. Falls back to LLM generation on miss."""
    # 1) Cache hit (quiz_items table keyed by keypoint_id + bloom_level)
    item = repo.get_quiz_by_kp_bloom(conn, keypoint_id, bloom, exclude_ids=used_ids)
    if item:
        return item

    # 2) Cache miss — generate grounded quiz via LLM
    kps = repo.get_keypoints(conn, concept_id)
    kp_meta = next((k for k in kps if k["id"] == keypoint_id), None)
    if not kp_meta:
        return None

    evidence = repo.get_chunk_text(conn, kp_meta.get("evidence_chunk_id") or "")
    if not evidence:
        return None

    spec = {
        "recall":        "Direct recall: ask what this key point IS. Short answer.",
        "comprehension": "Comprehension: ask the learner to explain WHY or HOW, or distinguish it from a common misconception. Short answer.",
        "application":   "Application: give a concrete scenario and ask whether/how this concept applies. Short answer.",
    }.get(bloom, "Short answer quiz question.")

    result = router.complete_json(
        f"Generate ONE quiz question STRICTLY grounded in the evidence below. "
        f"Do not add facts not in the evidence. JSON only:\n"
        f'{{"question": "<question text>", "answer_key": "<key phrase>", '
        f'"rubric": "<grading rubric>", "expected_keypoints": ["keyword1", "keyword2"]}}\n'
        f"Bloom level: {bloom} — {spec}\n"
        f"Key point: {kp_meta['name']}\n"
        f"Objective: {kp_meta['objective']}\n"
        f"Evidence: {evidence}",
        tier="cheap",
        stage="assess",
        fallback=None,
        session_id=session_id,
        conn=conn,
    )
    if not result or not result.get("question"):
        return None

    # 3) Generate MCQ distractors (overgenerate-rank), flaw-gate, estimate IRT difficulty
    question_text = result["question"]
    answer_key_text = result.get("answer_key", "")

    distractors = quizgen.make_distractors(
        question_text, answer_key_text,
        conn=conn, session_id=session_id,
        fallback=result.get("distractors") or [],
    )
    item_for_gate = {"question": question_text, "answer_key": answer_key_text,
                     "distractors": distractors}
    ok, reason = quizgen.flaw_gate(item_for_gate)
    if not ok:
        # Regenerate distractors once more on flaw failure
        distractors = quizgen.make_distractors(
            question_text, answer_key_text,
            conn=conn, session_id=session_id,
            fallback=result.get("distractors") or [],
        )
        item_for_gate = {"question": question_text, "answer_key": answer_key_text,
                         "distractors": distractors}
        ok2, _ = quizgen.flaw_gate(item_for_gate)
        if not ok2:
            # Still flawed: fall back to short-answer (empty distractors), do NOT crash
            distractors = []

    irt_b = quizgen.estimate_difficulty(
        {"question": question_text, "answer_key": answer_key_text},
        conn=conn, session_id=session_id,
    )

    # 4) Cache generated item back into quiz_items table
    generated_id = repo.create_quiz_item(
        conn,
        concept_id=concept_id,
        question=question_text,
        answer_key=answer_key_text,
        qtype="explain",
        difficulty={"recall": 1, "comprehension": 2, "application": 3}.get(bloom, 1),
        evidence_chunk_id=kp_meta["evidence_chunk_id"],
        source_paper_id=None,
        rubric=result.get("rubric"),
        expected_keypoints=str(result.get("expected_keypoints", [])),
        keypoint_id=keypoint_id,
        bloom_level=bloom,
        distractors_json=json.dumps(distractors),
        irt_b=irt_b,
    )
    return {
        "id": generated_id,
        "concept_id": concept_id,
        "keypoint_id": keypoint_id,
        "bloom_level": bloom,
        "question": question_text,
        "answer_key": answer_key_text,
        "rubric": result.get("rubric"),
        "expected_keypoints": str(result.get("expected_keypoints", [])),
        "evidence_chunk_id": kp_meta["evidence_chunk_id"],
        "distractors": distractors,
        "irt_b": irt_b,
    }


def assess_next_node(state: NavState, conn: sqlite3.Connection) -> dict:
    """Select the next quiz item and pose it. Graph interrupts here to await user answer."""
    cp = state["concept_progress"]
    bloom = cp.get("current_bloom") or BLOOM_LADDER[0]

    used_ids: list[int] = []
    for qr_entry in (state.get("history") or []):
        if qr_entry.get("event") == "grade_kp" and qr_entry.get("quiz_id"):
            used_ids.append(qr_entry["quiz_id"])

    # Pick the keypoint with the lowest mastery to quiz next
    kp_states = cp["keypoint_state"]
    target_kp_id = min(kp_states.items(), key=lambda kv: kv[1].get("mastery", 0.3))[0]

    # After a correct answer, upgrade bloom for the same keypoint
    last_kp = cp.get("current_keypoint_id")
    last_result = kp_states.get(last_kp, {}).get("last_result") if last_kp else None
    if last_result == "correct" and last_kp:
        cur_idx = BLOOM_LADDER.index(bloom)
        if cur_idx + 1 < len(BLOOM_LADDER):
            candidate = BLOOM_LADDER[cur_idx + 1]
            # Respect bloom_ceiling if set (OW-4 goal elicitation)
            ceiling = state.get("bloom_ceiling")
            if ceiling and ceiling in BLOOM_LADDER:
                ceiling_idx = BLOOM_LADDER.index(ceiling)
                if cur_idx + 1 > ceiling_idx:
                    candidate = None   # already at or beyond ceiling — don't upgrade
            if candidate is not None:
                bloom = candidate
                target_kp_id = last_kp  # stay on same keypoint at higher level

    quiz = _get_or_generate(conn, cp["concept_id"], target_kp_id, bloom, used_ids,
                            session_id=state["session_id"])
    reused = False
    if quiz is None and kp_states.get(target_kp_id, {}).get("last_result") == "wrong":
        # After a reteach, the learner still needs a same-level check. If the fixture only
        # has one cached quiz at this bloom, re-use it instead of dropping into a no-question
        # state. This preserves the teach -> reteach -> re-quiz loop offline.
        quiz = repo.get_quiz_by_kp_bloom(conn, target_kp_id, bloom, exclude_ids=[])
        reused = quiz is not None
    if quiz is None:
        # No quiz available at this bloom — fall through to route_decider
        return {
            "concept_progress": {**cp, "current_keypoint_id": target_kp_id, "current_bloom": bloom},
            "current_quiz_item": None,
            "rationale": f"No quiz available for keypoint '{target_kp_id}' at bloom={bloom} — skipping",
            "history": [{"event": "assess_skip", "keypoint_id": target_kp_id, "bloom": bloom}],
        }

    updated_cp = {**cp, "current_keypoint_id": target_kp_id, "current_bloom": bloom}

    return {
        "concept_progress": updated_cp,
        "current_quiz_item": quiz,
        "rationale": (
            f"ASSESS bloom={bloom} on keypoint '{target_kp_id}'"
            + (" (re-using prior quiz after reteach)" if reused else "")
        ),
        "history": [{
            "event": "assess_next",
            "keypoint_id": target_kp_id,
            "bloom": bloom,
            "quiz_id": quiz.get("id"),
            "question": quiz["question"],
            "reused": reused,
        }],
    }
