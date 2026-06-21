"""Worked-example renderer (spec §6.4).

Pipeline: cheap LLM → strict JSON ``{"steps":[...], "practice":{"question","answer"}}``
→ deterministic Markdown assembler.

Live path: ``router.complete_json(tier="cheap", stage="artifact", ...)`` asks the LLM
for a step-by-step worked example grounded in the supplied evidence, plus one practice
item (question + answer).
Offline/fallback path: ``_templated`` builds the same structure deterministically.
``_to_markdown`` is always deterministic — the LLM only shapes the content, never the
markup.
"""
from __future__ import annotations

import os
import sqlite3


def _templated(concept: dict, evidence: list[str]) -> dict:
    """Deterministic worked-example structure: steps + practice item.

    Derives steps from the concept name and first evidence/keypoint.
    Returns ``{"steps": [...], "practice": {"question": ..., "answer": ...}}``.
    """
    name = concept.get("name") or concept.get("slug") or "?"

    if evidence:
        raw = evidence[0].rstrip(".")
        steps = [
            f"Identify the concept: {name}.",
            f"Step 1 — understand the mechanism: {raw}.",
            "Step 2 — apply: substitute concrete values or a scenario into the mechanism above.",
            "Step 3 — verify: check the result against the expected outcome.",
        ]
        practice_q = f"In your own words, explain how {name} works based on the evidence."
        practice_a = f"{name} works by: {raw}."
    else:
        steps = [
            f"Identify the concept: {name}.",
            "Step 1 — recall: what is the core mechanism of this concept?",
            "Step 2 — apply: use the mechanism in a concrete scenario.",
            "Step 3 — verify: does the result match expectations?",
        ]
        practice_q = f"In your own words, explain how {name} works."
        practice_a = f"Refer to the evidence for {name} to construct your answer."

    return {
        "steps": steps,
        "practice": {"question": practice_q, "answer": practice_a},
    }


def _build_prompt(concept: dict, evidence: list[str]) -> str:
    name = concept.get("name") or concept.get("slug") or "?"
    lines = [
        f"Produce a step-by-step worked example for the concept '{name}' grounded ONLY in the evidence below.",
        "Rules: each step must be concrete and derived from the evidence; do NOT invent facts.",
        'Return ONLY valid JSON: {"steps":["<step text>",...],"practice":{"question":"<Q>","answer":"<A>"}}',
        "Include 3–5 numbered steps and exactly one practice item with a question and answer.",
        "",
        "Evidence:",
    ]
    for ev in evidence:
        lines.append(f"  - {ev}")
    return "\n".join(lines)


def _build(
    concept: dict,
    evidence: list[str],
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None,
) -> dict:
    """Return a worked-example dict from LLM or deterministic fallback."""
    from litnav.llm import router

    fallback = _templated(concept, evidence)
    prompt = _build_prompt(concept, evidence)

    result = router.complete_json(
        prompt,
        tier="cheap",
        stage="artifact",
        fallback=fallback,
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    # Validate: must be a dict with a list "steps" and a dict "practice"
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("steps"), list)
        or not isinstance(result.get("practice"), dict)
    ):
        return fallback
    return result


def _to_markdown(concept: dict, built: dict, citations: list[str]) -> str:
    """Deterministic Markdown assembler for one worked example.

    Structure:
        ## Worked Example: <name>
        numbered steps (1. ...)
        ### Practice
        **Q:** ...
        **Answer:** ...
        > Recall prompt: ...
        Citations: ...
    """
    name = concept.get("name") or concept.get("slug") or "?"
    steps: list[str] = built.get("steps") or []
    practice: dict = built.get("practice") or {}

    parts: list[str] = []

    parts.append(f"## Worked Example: {name}")
    parts.append("")

    for i, step in enumerate(steps, start=1):
        parts.append(f"{i}. {step}")
    parts.append("")

    parts.append("### Practice")
    parts.append("")
    question = practice.get("question", "")
    answer = practice.get("answer", "")
    parts.append(f"**Q:** {question}")
    parts.append("")
    parts.append(f"**Answer:** {answer}")
    parts.append("")

    parts.append("> Recall prompt: before revealing the answer, try to work through each step from memory.")
    parts.append("")

    cite_str = ", ".join(citations) if citations else "(none)"
    parts.append(f"Citations: {cite_str}")
    parts.append("")

    return "\n".join(parts)


def render(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    citations: list[str],
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None = None,
) -> str:
    """Render worked examples as a Markdown string.

    Parameters
    ----------
    concepts:
        Ordered list of ``{"slug": ..., "name": ...}`` dicts.
    evidence_by_concept:
        Map of slug → list of evidence strings (from the digest store).
    citations:
        List of citation IDs to append as a footer.
    conn, session_id:
        Passed through to the router for cost metering.
    budget:
        Optional token budget; forwarded to the router.
    """
    provider = os.environ.get("LITNAV_LLM_PROVIDER", "").lower()
    offline = provider in ("none", "offline")

    md_parts: list[str] = []

    for concept in concepts:
        slug = concept.get("slug") or (concept.get("name") or "").lower().replace(" ", "_")
        evidence = evidence_by_concept.get(slug) or []

        if offline:
            built = _templated(concept, evidence)
        else:
            built = _build(concept, evidence, conn=conn, session_id=session_id, budget=budget)

        # Per-section markdown (includes its own Citations line for simplicity)
        md_parts.append(_to_markdown(concept, built, citations))

    return "\n".join(md_parts)
