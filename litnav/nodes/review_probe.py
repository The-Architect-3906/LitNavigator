"""In-session spaced-retrieval probe (testing effect). Poses an EXISTING quiz for a mastered concept
that is due (>=k turns since last seen), grades it low-stakes, logs predicted-vs-actual retention, and
reinforces/flags — but never triggers a reteach and never blocks teaching.
Spec: docs/superpowers/specs/2026-06-22-spaced-retrieval-design.md."""
from __future__ import annotations

import sqlite3

from litnav.assess import retrieval, spacing
from litnav.llm import router
from litnav.state import NavState
from litnav.storage import repo


def pick_due_concept(state: NavState, conn: sqlite3.Connection, k: int = 2):
    """Return (concept_id, quiz_dict) for the most-overdue mastered concept with a stored quiz, else None."""
    last_seen = state.get("concept_last_seen") or {}
    step = state.get("step", 0)
    done = [s["concept_id"] for s in state.get("route", []) if s.get("status") == "done"]
    due = sorted((cid for cid in done if retrieval.is_due(last_seen.get(cid), step, k)),
                 key=lambda cid: last_seen.get(cid, 0))
    for cid in due:
        for kp in repo.get_keypoints(conn, cid):
            quiz = repo.get_any_quiz_for_kp(conn, kp["id"], exclude_ids=[])
            if quiz:
                return cid, quiz
    return None


def pose_probe(state: NavState, conn: sqlite3.Connection, k: int = 2) -> dict:
    """Pose a retrieval quiz for a due mastered concept (or pass-through with {} if nothing is due)."""
    picked = pick_due_concept(state, conn, k)
    if picked is None:
        return {}
    cid, quiz = picked
    step = state.get("step", 0)
    last_seen = {**(state.get("concept_last_seen") or {}), cid: step}
    item = {**quiz, "concept_id": cid, "is_retrieval": True}
    return {
        "current_quiz_item": item,
        "concept_last_seen": last_seen,
        "rationale": "Quick recap of an earlier concept before we move on.",
        "history": [{"event": "review_probe_pose", "concept_id": cid, "quiz_id": quiz.get("id")}],
    }


def grade_probe(state: NavState, conn: sqlite3.Connection) -> dict:
    """Grade the recap answer low-stakes: reinforce/nudge mastery, log retention, flag on miss. No reteach."""
    quiz = state.get("current_quiz_item") or {}
    cid = quiz.get("concept_id")
    answer = (state.get("pending_answers") or [""])[0] or ""
    ls = state.get("learner_state") or {}
    prior = ls.get(cid) or {}
    mastery_before = float(prior.get("mastery", 0.5))

    fallback = {"correct": quiz.get("answer_key", "").lower() in answer.lower()}
    verdict = router.complete_json(
        "Judge ONLY whether the answer conveys the expected key idea (accept paraphrases). JSON only.\n"
        f"Question: {quiz.get('question', '')}\nExpected: {quiz.get('answer_key', '')}\nAnswer: {answer!r}\n"
        '{"correct": true or false}',
        tier="cheap", stage="review_probe", fallback=fallback,
        session_id=state["session_id"], conn=conn,
    )
    correct = bool(verdict.get("correct"))
    new_mastery = retrieval.reinforce(mastery_before, correct)

    repo.upsert_learner_state(conn, state["session_id"], cid, mastery=new_mastery,
                              confidence=prior.get("confidence", 0.0),
                              n_observations=prior.get("n_observations", 0))
    learner_state = {**ls, cid: {**prior, "mastery": new_mastery}}
    spacing.log_retention(conn, state["session_id"], cid,
                          predicted=retrieval.predicted_recall(mastery_before),
                          actual=1.0 if correct else 0.0,
                          probed_at=state.get("now") or "")
    needs = list(state.get("needs_review") or [])
    if not correct and cid not in needs:
        needs.append(cid)
    return {
        "learner_state": learner_state,
        "needs_review": needs,
        "current_quiz_item": None,
        "rationale": (f"Recap correct — reinforced “{quiz.get('answer_key', '')[:30]}”."
                      if correct else "Recap slipped — flagged it for later review (no reteach)."),
        "history": [{"event": "review_probe_grade", "concept_id": cid, "correct": correct}],
    }
