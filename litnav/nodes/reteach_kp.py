"""ASSESS phase reteach node: re-teach only the specific keypoint that was answered wrong.

Picks the first unused strategy and loops back to assess_next at the same bloom level.
Includes a metacognitive opener ("which part felt unclear?") and never reveals the answer
key verbatim (anti-over-help, spec §6.3).
"""
from __future__ import annotations

import sqlite3

from litnav.assess import strategy as strat_policy
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

    # Pick a DIFFERENT strategy from prior attempts (anti-repetition).
    # Falls back to the last TEACH_STRATEGIES entry if all are exhausted.
    strategy = next((st for st in TEACH_STRATEGIES if st not in used), TEACH_STRATEGIES[-1])
    used.append(strategy)
    s["strategies_used"] = used
    s["reteach_count"] = s.get("reteach_count", 0) + 1

    bloom = cp["current_bloom"] or "recall"
    strategy_instructions = {
        "direct":         "Re-explain the key point clearly and directly.",
        "analogy":        "Use a concrete real-world analogy to make the key point intuitive.",
        "contrast":       "Contrast the correct idea with the most common misconception about it.",
        "worked_example": "Walk through a concrete worked example that illustrates the key point.",
    }
    instruction = strategy_instructions.get(strategy, "Re-explain the key point.")

    # Metacognitive opener: invite the learner to identify the sticking point.
    metacognitive_lead = (
        "First, briefly ask the learner which part felt unclear or confusing — "
        "what about this concept seemed stuck or hard to grasp. "
        "Then re-explain based on that gap."
    )

    language = state.get("target_language") or "English"

    # Anti-over-help guard: do NOT embed the answer key in the prompt.
    # (The answer_key is intentionally NOT passed here — spec §6.3.)
    anti_over_help = (
        "IMPORTANT: Do NOT state the answer outright. "
        "Guide the learner to the correct understanding without simply giving them the answer."
    )

    fallback = (
        f"Which part felt unclear? Let me re-explain **{kp_meta['name']}** "
        f"using a different approach.\n\n"
        f"{instruction}\n\n"
        f"From the paper: {evidence}"
    )
    explanation = router.complete_text(
        f"{metacognitive_lead}\n\n"
        f"A learner answered a {bloom}-level question about this key point incorrectly. "
        f"Re-teach ONLY this key point using the '{strategy}' strategy. "
        f"{instruction} Ground your explanation strictly in the evidence. "
        f"Be targeted and concise (3-4 sentences). Do NOT quiz. "
        f"Respond in {language}.\n\n"
        f"{anti_over_help}\n\n"
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
        "current_cited_chunks": [kp_meta["evidence_chunk_id"]] if kp_meta.get("evidence_chunk_id") else [],
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
