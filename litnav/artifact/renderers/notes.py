"""Cornell-style study notes renderer (spec §6.4).

Produces cue-column + explanation + summary notes grounded in the session evidence.
Live path uses a cheap LLM; offline path uses a deterministic template.
Citations are resolved to human-readable paper titles.
"""
from __future__ import annotations

import os
import sqlite3


_BLOOM_ORDER = {"recall": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}


def _resolve_citations(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[str]:
    """Map chunk IDs to readable paper references. Falls back to arXiv:ID then raw ID."""
    resolved = []
    seen: set[str] = set()
    for cid in chunk_ids:
        row = conn.execute(
            "SELECT p.title, p.year, p.url, p.arxiv_id FROM paper_chunks pc "
            "LEFT JOIN papers p ON p.id = pc.paper_id WHERE pc.id=?", (cid,)
        ).fetchone()
        if row:
            title, year, url, arxiv_id = row
            if title:
                label = f"{title} ({year})" if year else title
                if url:
                    label = f"[{label}]({url})"
            elif arxiv_id:
                label = f"arXiv:{arxiv_id}"
            else:
                label = cid
        else:
            label = cid
        if label not in seen:
            resolved.append(label)
            seen.add(label)
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


def _build_prompt(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    prereqs_by_concept: dict[str, list[str]],
    language: str = "English",
) -> str:
    lines = [
        "Produce Cornell-style study notes grounded ONLY in the evidence below.",
        "For each concept write:",
        "  - cues: 2-3 guiding questions a student should be able to answer",
        "  - explanation: 2-4 sentences capturing the core idea IN YOUR OWN WORDS (no verbatim copying)",
        "  - summary: one tight sentence — the single most important takeaway",
        "Rules: concise (Mayer coherence), no bullet padding, no filler phrases.",
        "If a concept has prerequisites listed, you may briefly reference them but do not re-explain them.",
        f"Write ALL output in {language}.",
        'Return JSON: {"notes":[{"concept":"<name>","cues":["<q1>","<q2>","<q3>"],'
        '"explanation":"<2-4 sentences>","summary":"<one sentence>"}]}',
        "",
        "Evidence:",
    ]
    for c in concepts:
        name = c.get("name") or c.get("slug") or "?"
        slug = c.get("slug") or name.lower().replace(" ", "_")
        evs = evidence_by_concept.get(slug) or []
        prereqs = prereqs_by_concept.get(slug) or []
        lines.append(f"  [{name}]" + (f"  (prereqs: {', '.join(prereqs)})" if prereqs else ""))
        for ev in evs[:4]:
            lines.append(f"    - {ev}")
    return "\n".join(lines)


def render(
    concepts: list[dict],
    evidence_by_concept: dict[str, list[str]],
    citations: list[str],
    *,
    conn: sqlite3.Connection,
    session_id: str,
    edges: list[dict] | None = None,
    bloom_by_concept: dict[str, str] | None = None,
    budget: int | None = None,
    language: str = "English",
) -> str:
    """Render Cornell-style study notes as a Markdown string."""
    edges = edges or []
    bloom_by_concept = bloom_by_concept or {}

    # Build name lookups from slug
    name_of: dict[str, str] = {c.get("slug", ""): (c.get("name") or c.get("slug") or "?") for c in concepts}

    # prereqs_by_concept[target_slug] = [prereq_name, ...]
    prereqs_by_concept: dict[str, list[str]] = {}
    for e in edges:
        if e.get("edge_type") == "prerequisite":
            tgt = e["target_slug"]
            pre_name = name_of.get(e["prereq_slug"], e["prereq_slug"])
            prereqs_by_concept.setdefault(tgt, []).append(pre_name)

    provider = os.environ.get("LITNAV_LLM_PROVIDER", "").lower()
    offline = provider in ("none", "offline")

    fallback_notes = _offline_template(concepts, evidence_by_concept)
    fallback = {"notes": fallback_notes}

    if offline:
        notes_list = fallback_notes
    else:
        from litnav.llm import router
        prompt = _build_prompt(concepts, evidence_by_concept, prereqs_by_concept, language=language)
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

    resolved_citations = _resolve_citations(conn, citations)

    # --- Render Markdown ---
    md_parts = ["# Study Notes", ""]

    for entry in notes_list:
        name = entry.get("concept", "?")
        slug = next((c["slug"] for c in concepts if c.get("name") == name), name.lower().replace(" ", "_"))
        cues = entry.get("cues") or []
        explanation = entry.get("explanation", "").strip()
        summary = entry.get("summary", "").strip()

        bloom = bloom_by_concept.get(slug)
        prereqs = prereqs_by_concept.get(slug)

        md_parts.append(f"## {name}")

        # Metadata line — bloom level + prerequisite chain
        meta_parts = []
        if bloom:
            meta_parts.append(f"Bloom: **{bloom}**")
        if prereqs:
            meta_parts.append(f"Prerequisite: {', '.join(prereqs)}")
        if meta_parts:
            md_parts.append(f"*{' · '.join(meta_parts)}*")
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
