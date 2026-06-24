"""Cornell-style study notes renderer (spec §6.4).

Produces cue-column + explanation + summary notes grounded in the session evidence.
Live path uses a cheap LLM; offline path uses a deterministic template.
Citations are resolved to human-readable paper titles.
"""
from __future__ import annotations

import os
import sqlite3


def _resolve_citations(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[str]:
    """Map chunk IDs to readable paper references (Title, year). Falls back to chunk ID."""
    resolved = []
    seen: set[str] = set()
    for cid in chunk_ids:
        row = conn.execute(
            "SELECT p.title, p.year, p.url FROM paper_chunks pc "
            "LEFT JOIN papers p ON p.id = pc.paper_id WHERE pc.id=?", (cid,)
        ).fetchone()
        if row and row[0]:
            title, year, url = row
            label = f"{title} ({year})" if year else title
            if url:
                label = f"[{label}]({url})"
            if label not in seen:
                resolved.append(label)
                seen.add(label)
        else:
            if cid not in seen:
                resolved.append(cid)
                seen.add(cid)
    return resolved


def _offline_template(concepts: list[dict], evidence_by_concept: dict[str, list[str]]) -> list[dict]:
    """Build Cornell note entries without an LLM."""
    notes_list = []
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []

        cues = [
            f"What is {name} and why does it matter?",
            f"How does {name} work in practice?",
        ]

        # Build explanation from first 2 evidence items
        if evs:
            explanation = " ".join(ev.rstrip(".") + "." for ev in evs[:2])
        else:
            explanation = f"{name} is a key concept in this domain."

        # Short summary — trimmed from concept name + first evidence
        if evs:
            words = evs[0].rstrip(".").split()
            hint = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
            summary = hint
        else:
            summary = f"Core idea: see explanation above."

        notes_list.append({
            "concept": name,
            "cues": cues,
            "explanation": explanation,
            "summary": summary,
        })
    return notes_list


def _build_prompt(concepts: list[dict], evidence_by_concept: dict[str, list[str]],
                  language: str = "English") -> str:
    lines = [
        "Produce Cornell-style study notes grounded ONLY in the evidence below.",
        "For each concept write:",
        "  - cues: 2-3 guiding questions a student should be able to answer",
        "  - explanation: 2-4 sentences capturing the core idea IN YOUR OWN WORDS (no verbatim copying)",
        "  - summary: one tight sentence — the single most important takeaway",
        "Rules: concise (Mayer coherence), no bullet padding, no filler phrases.",
        f"Write ALL output in {language}.",
        'Return JSON: {"notes":[{"concept":"<name>","cues":["<q1>","<q2>"],'
        '"explanation":"<2-4 sentences>","summary":"<one sentence>"}]}',
        "",
        "Evidence:",
    ]
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []
        lines.append(f"  [{name}]")
        for ev in evs[:4]:  # cap per-concept evidence to keep prompt tight
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
    language: str = "English",
) -> str:
    """Render Cornell-style study notes as a Markdown string."""
    provider = os.environ.get("LITNAV_LLM_PROVIDER", "").lower()
    offline = provider in ("none", "offline")

    fallback_notes = _offline_template(concepts, evidence_by_concept)
    fallback = {"notes": fallback_notes}

    if offline:
        notes_list = fallback_notes
    else:
        from litnav.llm import router
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
        notes_list = result.get("notes") or fallback_notes

    # Resolve citations to human-readable paper references
    resolved_citations = _resolve_citations(conn, citations)

    # --- Render Markdown ---
    md_parts = ["# Study Notes", ""]

    for entry in notes_list:
        name = entry.get("concept", "?")
        cues = entry.get("cues") or []
        explanation = entry.get("explanation", "").strip()
        summary = entry.get("summary", "").strip()

        md_parts.append(f"## {name}")
        md_parts.append("")

        if explanation:
            md_parts.append(explanation)
            md_parts.append("")

        if cues:
            md_parts.append("**Self-test questions:**")
            for cue in cues:
                md_parts.append(f"- {cue}")
            md_parts.append("")

        if summary:
            md_parts.append(f"**Key takeaway:** {summary}")
            md_parts.append("")

        md_parts.append("> *Without looking, answer each question above from memory.*")
        md_parts.append("")
        md_parts.append("---")
        md_parts.append("")

    if resolved_citations:
        md_parts.append("## Sources")
        md_parts.append("")
        for ref in resolved_citations:
            md_parts.append(f"- {ref}")
        md_parts.append("")

    return "\n".join(md_parts)
