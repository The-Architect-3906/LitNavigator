"""handle_lost: respond when the learner says they're confused / need basics.

Two cases:
  A) Currently in ASSESS (concept_progress set) → re-explain the current keypoint
     with a simpler strategy (analogy > worked_example > contrast > direct).
  B) No concept_progress (legacy path or between concepts) → re-explain the current
     concept with simpler language.

Never grades, never records a quiz attempt, never advances mastery.
After re-explaining, routes back to assess_next (or check) so the SAME question
is re-posed with fresh context.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.state import NavState
from litnav.storage import repo

_SIMPLE_FIRST = ["analogy", "worked_example", "contrast", "direct"]


def handle_lost_node(state: NavState, conn: sqlite3.Connection) -> dict:
    cp = state.get("concept_progress")
    ack = "No problem — let me back up and try a different angle.\n\n"

    if cp and cp.get("current_keypoint_id"):
        # ── Case A: inside ASSESS, re-explain the current keypoint ───────────
        kp_id = cp["current_keypoint_id"]
        bloom = cp.get("current_bloom") or "recall"

        kps = repo.get_keypoints(conn, cp["concept_id"])
        kp_meta = next((k for k in kps if k["id"] == kp_id), None)
        evidence = repo.get_chunk_text(conn, kp_meta["evidence_chunk_id"] or "") if kp_meta else ""
        name = kp_meta["name"] if kp_meta else kp_id

        kp_s = dict(cp["keypoint_state"].get(kp_id, {}))
        used = list(kp_s.get("strategies_used", []))
        strategy = next((s for s in _SIMPLE_FIRST if s not in used), _SIMPLE_FIRST[0])
        used.append(strategy)
        kp_s["strategies_used"] = used

        strategy_desc = {
            "analogy":        "Use a concrete real-world analogy.",
            "worked_example": "Walk through a step-by-step worked example.",
            "contrast":       "Contrast the correct idea with the most common misconception.",
            "direct":         "Re-state the key idea as simply as possible.",
        }.get(strategy, "Re-explain simply.")

        fallback = (
            f"{ack}**{name}** ({strategy})\n\n"
            f"{strategy_desc}\n\n{evidence[:250]}"
        )
        explanation = llm_client.complete_text(
            f"The learner said they're confused. Re-explain ONLY this key point using a "
            f"'{strategy}' approach ({strategy_desc}). "
            f"Be very concrete and accessible. 2-4 sentences. Do NOT quiz.\n\n"
            f"Key point: {name}\nEvidence: {evidence}",
            fallback=fallback,
            max_tokens=220,
        )
        text = ack + explanation

        new_kp_state = {**cp["keypoint_state"], kp_id: kp_s}
        updated_cp = {**cp, "keypoint_state": new_kp_state}

        return {
            "concept_progress": updated_cp,
            "user_intent": None,
            "rationale": f"LOST: re-explaining '{kp_id}' at bloom={bloom} with strategy='{strategy}'",
            "history": [{
                "event": "handle_lost",
                "keypoint_id": kp_id,
                "bloom": bloom,
                "strategy": strategy,
                "text": text,
            }],
        }

    else:
        # ── Case B: legacy path — re-explain the current concept ─────────────
        concept_id = state.get("current_concept_id")
        name = None
        if concept_id is not None:
            row = conn.execute("SELECT name FROM concepts WHERE id=?", (concept_id,)).fetchone()
            name = row[0] if row else f"concept {concept_id}"

        evidence_chunks = state.get("current_evidence") or []
        evidence = evidence_chunks[0]["text"] if evidence_chunks else ""

        strategy = "analogy"
        fallback = (
            f"{ack}**{name or 'this concept'}** (analogy)\n\n"
            f"Let me try explaining with a concrete analogy.\n\n{evidence[:250]}"
        )
        explanation = llm_client.complete_text(
            f"The learner said they're lost. Re-explain the concept '{name}' using a vivid "
            f"real-world analogy. 2-4 sentences. Do NOT quiz.\n\nEvidence: {evidence}",
            fallback=fallback,
            max_tokens=220,
        )
        text = ack + explanation

        return {
            "user_intent": None,
            "rationale": f"LOST: re-explaining concept '{name}' with analogy strategy",
            "history": [{
                "event": "handle_lost",
                "concept_id": concept_id,
                "strategy": strategy,
                "text": text,
            }],
        }
