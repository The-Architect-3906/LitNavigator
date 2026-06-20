"""Map a learner's free-text goal to a tutor action (the agent's front door).

LLM-backed when a provider is set, with a deterministic keyword fallback so it works
offline and in tests. The LLM only *classifies* into a known slug — validated against the
candidate set, so a hallucinated slug can never start a bogus session.
"""
from __future__ import annotations

from litnav.llm import client as llm_client


def _deterministic(goal: str, concepts: list[dict], off: dict | None) -> dict:
    text = goal.lower()
    if off:
        aliases = {off["slug"].replace("_", " "), off["name"].lower(), "debate"}
        if any(a and a in text for a in aliases):
            return {"kind": "induce", "slug": off["slug"], "name": off["name"]}
    # Pass 1: slug-phrase match across all concepts (longest wins).
    # Done as a separate pass so a short word from one concept's name (e.g. "agent" from
    # "Agent memory") can't intercept before a longer slug phrase ("multi agent") is checked.
    slug_hits = [(len(c["slug"].replace("_", " ")), c)
                 for c in concepts if c["slug"].replace("_", " ") in text]
    if slug_hits:
        slug_hits.sort(key=lambda x: -x[0])
        c = slug_hits[0][1]
        return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
    # Pass 2: word-level fallback (concept-order; first match wins).
    for c in concepts:
        for word in c["name"].lower().replace("(", " ").replace(")", " ").split():
            if len(word) > 3 and word in text:
                return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
    return {"kind": "unknown", "available": [c["name"] for c in concepts]}


def resolve_goal(goal: str, concepts: list[dict], off: dict | None = None) -> dict:
    """Return one of:
        {"kind": "concept", "slug", "name"}    -> plan a route to this curated concept
        {"kind": "induce",  "slug", "name"}    -> induce the off-skeleton scaffold, then teach
        {"kind": "unknown", "available": [..]} -> goal is outside this corpus
    """
    if not (goal or "").strip():
        return {"kind": "unknown", "available": [c["name"] for c in concepts]}
    fallback = _deterministic(goal, concepts, off)

    off_line = f"{off['slug']} ({off['name']})" if off else "(none)"
    prompt = (
        "A learner stated a learning goal. Map it to exactly one option below.\n"
        f"Goal: {goal!r}\n"
        f"Curated concepts (slug: name): {[(c['slug'], c['name']) for c in concepts]}\n"
        f"Off-skeleton concept to INDUCE only if explicitly requested: {off_line}\n"
        'Respond as JSON: {"slug": "<the matching slug, the off-skeleton slug, or null>"}'
    )
    result = llm_client.complete_json(prompt, fallback={"slug": None})
    slug = result.get("slug")

    if off and slug == off["slug"]:
        return {"kind": "induce", "slug": off["slug"], "name": off["name"]}
    by_slug = {c["slug"]: c for c in concepts}
    if slug in by_slug:
        c = by_slug[slug]
        return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
    return fallback  # null/unknown/hallucinated -> deterministic keyword match
