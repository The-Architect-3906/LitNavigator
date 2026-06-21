"""Marp slides renderer (spec §6.4).

Pipeline: cheap LLM → strict JSON outline → deterministic Marp Markdown emitter.

Live path: ``router.complete_json(tier="cheap", stage="artifact", ...)`` asks the LLM
for ``{"slides":[{"title":"...","bullets":["..."]}]}``.
Offline/fallback path: ``_templated_outline`` builds the same structure deterministically.
``_to_marp`` is always deterministic — the LLM only shapes the outline, never the markup.
"""
from __future__ import annotations

import os
import sqlite3


def _templated_outline(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
) -> dict:
    """Deterministic outline: one slide per concept, bullets from evidence/keypoints."""
    slide_list = []
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []

        bullets: list[str] = []
        for ev in evs[:3]:                       # at most 3 bullets per concept
            raw = ev.rstrip(".")
            words = raw.split()
            bullet = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
            bullets.append(bullet)
        if not bullets:
            bullets = [f"Key concept: {name}"]

        slide_list.append({"title": name, "bullets": bullets})

    return {"slides": slide_list}


def _build_prompt(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    language: str = "English",
) -> str:
    lines = [
        "Produce a concise Marp slide outline grounded ONLY in the evidence below.",
        "Rules: apply Mayer's coherence principle — short bullets, no verbatim copying.",
        f"Write ALL output in {language}.",
        'Return ONLY valid JSON: {"slides":[{"title":"<name>","bullets":["<short point>"]}]}',
        "One slide entry per concept. At most 4 bullets per slide.",
        "",
        "Evidence:",
    ]
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []
        lines.append(f"  [{name}]")
        for ev in evs:
            lines.append(f"    - {ev}")
    return "\n".join(lines)


def _outline(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None,
    language: str = "English",
) -> dict:
    """Return a ``{"slides": [...]}`` outline dict from LLM or deterministic fallback."""
    from litnav.llm import router

    fallback = _templated_outline(concepts, evidence_by_concept)
    prompt = _build_prompt(concepts, evidence_by_concept, language=language)

    result = router.complete_json(
        prompt,
        tier="cheap",
        stage="artifact",
        fallback=fallback,
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    # Validate: must be a dict with a non-empty list under "slides"
    if not isinstance(result, dict) or not isinstance(result.get("slides"), list):
        return fallback
    return result


def _to_marp(outline: dict, citations: list[str]) -> str:
    """DETERMINISTIC Marp Markdown emitter.

    Structure:
        front-matter block  (---\\nmarp: true\\n---)
        title slide
        one content slide per outline entry  (## title + bullets + retrieval prompt)
        citations slide
    """
    parts: list[str] = []

    # ── Marp front-matter ──────────────────────────────────────────────────
    parts.append("---")
    parts.append("marp: true")
    parts.append("theme: default")
    parts.append("paginate: true")
    parts.append("---")

    # ── Title slide ────────────────────────────────────────────────────────
    parts.append("")
    parts.append("# Study Slides")
    parts.append("")
    parts.append("*LitNavigator · generated*")
    parts.append("")

    # ── Content slides ─────────────────────────────────────────────────────
    slides_list = outline.get("slides") or []
    for slide in slides_list:
        parts.append("\n---\n")
        title = slide.get("title", "?")
        bullets = slide.get("bullets") or []
        parts.append(f"## {title}")
        parts.append("")
        for b in bullets:
            parts.append(f"- {b}")
        parts.append("")
        parts.append("> Recall prompt: without looking, explain this concept in your own words.")
        parts.append("")

    # ── Citations slide ────────────────────────────────────────────────────
    parts.append("\n---\n")
    parts.append("## Citations")
    parts.append("")
    cite_str = ", ".join(citations) if citations else "(none)"
    parts.append(f"Sources: {cite_str}")
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
    language: str = "English",
) -> str:
    """Render a Marp Markdown slide deck as a string.

    Parameters
    ----------
    concepts:
        Ordered list of ``{"slug": ..., "name": ...}`` dicts.
    evidence_by_concept:
        Map of slug → list of evidence strings (from the digest store).
    citations:
        List of citation IDs to include on the final Citations slide.
    conn, session_id:
        Passed through to the router for cost metering.
    budget:
        Optional token budget; forwarded to the router.
    language:
        The learner's output language (e.g. "Chinese"). Injected into the LLM prompt.
        Offline/template path is language-neutral (structural Markdown only).
    """
    provider = os.environ.get("LITNAV_LLM_PROVIDER", "").lower()
    offline = provider in ("none", "offline")

    if offline:
        outline = _templated_outline(concepts, evidence_by_concept)
    else:
        outline = _outline(concepts, evidence_by_concept,
                           conn=conn, session_id=session_id, budget=budget,
                           language=language)

    return _to_marp(outline, citations)
