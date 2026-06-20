"""ORIENT phase: give a roadmap overview before diving into individual concepts.

Called once per session when the route has more than one concept.  Shows the learner
the conceptual path they're about to walk (prereqs first → target) so they have a
mental model before any teaching begins.  No quiz, no mastery updates.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.state import NavState


def orient_tour_node(state: NavState, conn: sqlite3.Connection) -> dict:
    route = state["route"]
    concept_ids = [s["concept_id"] for s in route]

    rows = {
        r[0]: {"name": r[1], "desc": r[2] or ""}
        for r in conn.execute(
            f"SELECT id, name, description FROM concepts WHERE id IN ({','.join('?'*len(concept_ids))})",
            concept_ids,
        ).fetchall()
    }

    stops = [rows[cid] for cid in concept_ids if cid in rows]

    if len(stops) <= 1:
        # Single concept — no roadmap needed; skip silently
        return {
            "orient_done": True,
            "history": [{"event": "orient_tour", "text": None, "skipped": True}],
        }

    # Build a brief connector sentence per concept
    bullets = "\n".join(
        f"  {i+1}. **{s['name']}**"
        + (f" — {s['desc'][:90].rstrip()}…" if len(s['desc']) > 20 else "")
        for i, s in enumerate(stops)
    )

    fallback = (
        f"Before we dive in, here's the roadmap for this session:\n\n"
        f"{bullets}\n\n"
        f"Each concept builds on the previous one. "
        f"We'll work through them in order, starting with **{stops[0]['name']}**. "
        f"Let me know if you'd like to slow down or revisit anything at any point."
    )

    prompt = (
        "You are an expert tutor giving a learner a 3-5 sentence roadmap overview before "
        "teaching a sequence of research concepts. Use plain language. Do NOT teach yet — "
        "just orient: name each concept, explain in one clause how it connects to the next, "
        "and end with 'We'll start with [first concept].'\n\n"
        f"Ordered concept sequence:\n{bullets}"
    )
    text = llm_client.complete_text(prompt, fallback=fallback, max_tokens=250)

    return {
        "orient_done": True,
        "rationale": f"ORIENT: roadmap overview for {len(stops)}-concept route",
        "history": [{
            "event": "orient_tour",
            "text": text,
            "concepts": [s["name"] for s in stops],
        }],
    }
