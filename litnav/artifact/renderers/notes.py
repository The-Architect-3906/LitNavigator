"""Cornell-style concise notes renderer (spec §6.4).

Produces cue-column + summary notes — NOT verbatim evidence — plus a retrieval
prompt per concept and a citations footer.  Live path uses a cheap LLM grounded
in the supplied evidence; offline path uses a deterministic template.
"""
from __future__ import annotations

import os
import sqlite3


def _offline_template(concepts: list[dict], evidence_by_concept: dict[str, list[str]]) -> list[dict]:
    """Build Cornell note entries without an LLM.

    Each entry has:
    - concept: display name
    - cues: one question derived from the concept name (not the raw evidence sentence)
    - summary: a short condensed phrase (concept name + a trimmed clause), never
                a verbatim copy of the evidence text.
    """
    notes_list = []
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []

        cue = f"What is {name} and why does it matter?"

        # Build a short summary from the concept name plus a trimmed hint from evidence —
        # deliberately avoiding a verbatim copy of any evidence sentence.
        if evs:
            # Take first evidence item, strip the trailing period, truncate to ≤6 words.
            raw = evs[0].rstrip(".")
            words = raw.split()
            hint = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
            summary = f"{name}: {hint}"
        else:
            summary = f"{name}: key concept — see evidence for details."

        notes_list.append({"concept": name, "cues": [cue], "summary": summary})
    return notes_list


def _build_prompt(concepts: list[dict], evidence_by_concept: dict[str, list[str]]) -> str:
    lines = [
        "Produce Cornell-style study notes grounded ONLY in the evidence below.",
        "Rules: concise (Mayer's coherence principle) — do NOT copy sentences verbatim;",
        "distil each concept into meaningful cues (questions) and a SHORT summary phrase.",
        "Return JSON: {\"notes\":[{\"concept\":\"<name>\",\"cues\":[\"<q>\"],\"summary\":\"<short phrase>\"}]}",
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


def render(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    citations: list[str],
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None = None,
) -> str:
    """Render Cornell-style study notes as a Markdown string.

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

    # Build the offline fallback unconditionally (used by router when provider=none,
    # and also used as the fallback= value so the router never raises on schema errors).
    fallback_notes = _offline_template(concepts, evidence_by_concept)
    fallback = {"notes": fallback_notes}

    if offline:
        notes_list = fallback_notes
    else:
        from litnav.llm import router
        prompt = _build_prompt(concepts, evidence_by_concept)
        result = router.complete_json(
            prompt,
            tier="cheap",
            stage="artifact",
            fallback=fallback,
            session_id=session_id,
            conn=conn,
            budget=budget,
        )
        notes_list = result.get("notes") or fallback_notes

    # --- Render Markdown ---
    md_parts = ["# Study notes", ""]

    for entry in notes_list:
        name = entry.get("concept", "?")
        cues = entry.get("cues") or []
        summary = entry.get("summary", "")

        md_parts.append(f"## {name}")
        md_parts.append("")
        md_parts.append("**Cues:**")
        for cue in cues:
            md_parts.append(f"- {cue}")
        md_parts.append("")
        md_parts.append(f"**Summary:** {summary}")
        md_parts.append("")
        md_parts.append("> Recall prompt: without looking, answer each cue above from memory.")
        md_parts.append("")

    cite_str = ", ".join(citations) if citations else "(none)"
    md_parts.append(f"Citations: {cite_str}")
    md_parts.append("")

    return "\n".join(md_parts)
