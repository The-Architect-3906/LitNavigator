from __future__ import annotations

MASTERY_THRESHOLD = 0.8
MAX_RETEACH = 2


def tutor_router(state: dict) -> str:
    concept_id = state["current_concept_id"]
    threshold = state.get("mastery_threshold", MASTERY_THRESHOLD)
    cs = state["learner_state"].get(concept_id, {})
    mastery = cs.get("mastery", 0.0)
    misconceptions = cs.get("held_misconceptions", [])
    reteach_count = state.get("reteach_count", {}).get(concept_id, 0)
    prereqs = state.get("concept_dag", {}).get(concept_id, [])

    if mastery >= threshold:
        return "advance"

    # A prereq counts as "met" if mastery is high enough OR if it has already
    # been attempted in this session (route step status == "done").
    done_ids = {s["concept_id"] for s in state.get("route", []) if s.get("status") == "done"}
    unmastered_prereqs = [
        p for p in prereqs
        if state["learner_state"].get(p, {}).get("mastery", 0.0) < threshold
        and p not in done_ids
    ]
    if unmastered_prereqs:
        return "diagnose"

    if misconceptions and reteach_count < MAX_RETEACH:
        return "reteach"

    return "concede"
