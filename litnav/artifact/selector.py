"""Format-selection matrix (spec §6.4). Deterministic — no LLM."""
from __future__ import annotations
from litnav.artifact.contract import FORMATS


def select_format(scenario: dict, override: str | None = None) -> str:
    if override in FORMATS:
        return override
    gt = (scenario.get("goal_type") or "").lower()
    ck = (scenario.get("content_kind") or "").lower()
    req = (scenario.get("user_request") or "").lower()
    blob = f"{ck} {req}"
    if any(w in blob for w in ("slide", "deck", "present", "talk")):
        return "slides"
    if gt == "functional" or any(w in blob for w in ("procedure", "applied", "how to", "how-to", "build", "implement")):
        return "worked_example"
    if gt == "mastery":
        return "combination"
    if gt in ("survey", "systematic") or any(w in blob for w in ("structure", "map", "relate", "overview", "how concepts")):
        return "mindmap"
    return "notes"   # default: reference / crash-course / quick recall
