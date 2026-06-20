"""ASSESS phase reteach node: re-teach only the specific keypoint that was answered wrong.

Picks the first unused strategy and loops back to assess_next at the same bloom level.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import router
from litnav.state import TEACH_STRATEGIES, NavState
from litnav.storage import repo


def reteach_kp_node(state: NavState, conn: sqlite3.Connection) -> dict:
    cp = state["concept_progress"]
    kp_id = cp["current_keypoint_id"]

    kps = repo.get_keypoints(conn, cp["concept_id"])
    kp_meta = next((k for k in kps if k["id"] == kp_id), None)
    if kp_meta is None:
        return {}

    evidence = repo.get_chunk_text(conn, kp_meta["evidence_chunk_id"] or "")
    s = dict(cp["keypoint_state"].get(kp_id, {}))
    used = list(s.get("strategies_used", []))
    strategy = next((st for st in TEACH_STRATEGIES if st not in used), TEACH_STRATEGIES[-1])
    used.append(strategy)
    s["strategies_used"] = used
    s["reteach_count"] = s.get("reteach_count", 0) + 1

    bloom = cp["current_bloom"] or "recall"
    strategy_instructions = {
        "direct":       "Re-explain the key point clearly and directly.",
        "analogy":      "Use a concrete real-world analogy to make the key point intuitive.",
        "contrast":     "Contrast the correct idea with the most common misconception about it.",
        "worked_example": "Walk through a concrete worked example that illustrates the key point.",
    }
    instruction = strategy_instructions.get(strategy, "Re-explain the key point.")

    fallback = (
        f"Let me re-explain **{kp_meta['name']}** using a different approach.\n\n"
        f"{instruction}\n\n"
        f"From the paper: {evidence}"
    )
    explanation = router.complete_text(
        f"A learner answered a {bloom}-level question about this key point incorrectly. "
        f"Re-teach ONLY this key point using the '{strategy}' strategy. "
        f"{instruction} Ground your explanation strictly in the evidence. "
        f"Be targeted and concise (3-4 sentences). Do NOT quiz.\n\n"
        f"Key point: {kp_meta['name']}\n"
        f"Objective: {kp_meta['objective']}\n"
        f"Evidence: {evidence}",
        tier="cheap",
        stage="reteach",
        fallback=fallback,
        session_id=state["session_id"],
        conn=conn,
        max_tokens=250,
    )

    kp_state = {**cp["keypoint_state"], kp_id: s}
    updated_cp = {**cp, "keypoint_state": kp_state}

    rationale = (
        f"RETEACH keypoint '{kp_id}' at bloom={bloom} "
        f"using strategy='{strategy}' "
        f"(attempt {s['reteach_count']}/2)"
    )
    repo.record_decision(
        conn, state["session_id"], state["route_version"],
        "grade_kp", "reteach", rationale,
        state_snapshot={"keypoint_id": kp_id, "bloom": bloom,
                        "strategy": strategy, "count": s["reteach_count"]},
    )

    return {
        "concept_progress": updated_cp,
        "rationale": rationale,
        "history": [{
            "event": "reteach_kp",
            "keypoint_id": kp_id,
            "bloom": bloom,
            "strategy": strategy,
            "reteach_count": s["reteach_count"],
            "text": explanation,
        }],
    }
