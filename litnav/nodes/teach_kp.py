"""TEACH phase node: teach one keypoint per call, no quiz.

Called in a loop until all keypoints for the current concept are taught,
then the graph transitions to the ASSESS phase (assess_next).
Uses a deterministic strategy policy (goal_type × expertise × KT mastery) per spec §6.3.
"""
from __future__ import annotations

import sqlite3

from litnav.assess import strategy as strat_policy
from litnav.llm import router
from litnav.state import ConceptProgress, KeyPointState, NavState
from litnav.storage import repo


def init_concept_progress(concept_id: int, conn: sqlite3.Connection) -> ConceptProgress:
    """Build a fresh ConceptProgress for a concept entering the TEACH phase."""
    kps = repo.get_keypoints(conn, concept_id)
    return {
        "concept_id": concept_id,
        "phase": "teaching",
        "keypoints": [k["id"] for k in kps],
        "taught_idx": 0,
        "current_keypoint_id": None,
        "current_bloom": None,
        "keypoint_state": {
            k["id"]: KeyPointState(
                keypoint_id=k["id"],
                mastery=0.3,
                correct_obs=0,
                last_result=None,
                reteach_count=0,
                strategies_used=[],
            )
            for k in kps
        },
        "misconceptions": {},
    }


def teach_kp_node(state: NavState, conn: sqlite3.Connection) -> dict:
    """Teach the next untaught keypoint. Does NOT pose a quiz."""
    cp: ConceptProgress = state["concept_progress"]
    kp_id = cp["keypoints"][cp["taught_idx"]]

    kps = repo.get_keypoints(conn, cp["concept_id"])
    kp_meta = next((k for k in kps if k["id"] == kp_id), None)
    if kp_meta is None:
        return {"concept_progress": {**cp, "taught_idx": cp["taught_idx"] + 1}}

    evidence = repo.get_chunk_text(conn, kp_meta["evidence_chunk_id"] or "")
    new_idx = cp["taught_idx"] + 1
    is_last = new_idx >= len(cp["keypoints"])

    # Compute teaching strategy from the policy: goal × expertise × KT mastery (spec §6.3)
    kp_mastery = cp["keypoint_state"].get(kp_id, {}).get("mastery", 0.3) if cp.get("keypoint_state") else 0.3
    teach_strategy = strat_policy.choose_strategy(
        goal_type=state.get("goal_type"),
        expertise=state.get("intent"),   # "researcher" maps to expert mode if present
        mastery=kp_mastery,
    )

    strategy_clause = {
        "concise":        "Be concise and precise — the learner has strong prior knowledge.",
        "overview":       "Give a high-level overview; breadth matters more than depth here.",
        "worked_example": "Ground the explanation in a concrete worked example.",
        "analogy":        "Use a relatable real-world analogy to build intuition.",
        "direct":         "Explain directly and clearly.",
    }.get(teach_strategy, "Explain clearly and concisely.")

    language = state.get("target_language") or "English"

    fallback = (
        f"**{kp_meta['name']}**\n\n"
        f"Objective: {kp_meta['objective']}\n\n"
        f"From the paper: {evidence}"
    )
    explanation = router.complete_text(
        f"You are tutoring a researcher who is new to this subfield. "
        f"Teach ONLY the following key point, grounded strictly in the provided evidence. "
        f"Do NOT quiz or ask questions. "
        f"Teach using a '{teach_strategy}' approach: {strategy_clause} "
        f"Be clear and concise (3-5 sentences). "
        f"Respond in {language}.\n\n"
        f"Key point: {kp_meta['name']}\n"
        f"Learning objective: {kp_meta['objective']}\n"
        f"Evidence (cite this as your source): {evidence}",
        tier="cheap",
        stage="teach",
        fallback=fallback,
        session_id=state["session_id"],
        conn=conn,
        max_tokens=300,
    )

    updated_cp = {
        **cp,
        "taught_idx": new_idx,
        "current_keypoint_id": kp_id,
    }

    closing = "\n\nNow let's check your understanding." if is_last else None

    return {
        "concept_progress": updated_cp,
        "rationale": (
            f"TEACH keypoint {new_idx}/{len(cp['keypoints'])}: '{kp_meta['name']}' "
            f"(no quiz yet — full lecture pass first)"
        ),
        "history": [{
            "event": "teach_kp",
            "concept_id": cp["concept_id"],
            "keypoint_id": kp_id,
            "idx": new_idx,
            "total": len(cp["keypoints"]),
            "text": explanation,
            "closing": closing,
        }],
    }


def route_after_teach_kp(state: NavState) -> str:
    """Continue teaching if keypoints remain; switch to ASSESS when all taught."""
    cp: ConceptProgress = state["concept_progress"]
    if cp["taught_idx"] < len(cp["keypoints"]):
        return "teach_kp"
    return "assess_next"
