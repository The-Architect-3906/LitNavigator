"""Deterministic mind-map renderer: Mermaid graph from the concept graph (spec §6.4). No LLM."""
from __future__ import annotations
import re


def _safe(text: str) -> str:
    # Mermaid node label: strip quotes/brackets that break the syntax
    return re.sub(r'[\"\[\]\(\)\{\}|]', " ", str(text)).strip() or "?"


def render(graph: dict, citations: list[str]) -> str:
    concepts = graph.get("concepts") or []
    edges = graph.get("edges") or []
    lines = ["```mermaid", "graph TD"]
    for c in concepts:
        slug = c.get("slug") or c.get("id")
        lines.append(f'    {slug}["{_safe(c.get("name", slug))}"]')
    for e in edges:
        a, b = e.get("prereq_slug"), e.get("target_slug")
        if a is None or b is None:
            continue
        arrow = "-->" if e.get("edge_type") == "prerequisite" else "-.->"
        lines.append(f"    {a} {arrow} {b}")
    lines.append("```")
    body = "\n".join(lines)
    prompt = "\n\n> **Recall prompt:** without looking, name the prerequisite of each concept above and one link between two of them."
    cites = "\n\nCitations: " + (", ".join(citations) if citations else "(none)")
    return f"# Concept map\n\n{body}{prompt}{cites}\n"
