"""RefD-style prerequisite signal (Liang et al. 2015) over the digest chunks.
B is a prerequisite of A when A's context references B more than B references A — a non-LLM corpus
signal that complements the LLM proposal/judge (spec §6.2 'RefD-style + LLM')."""
from __future__ import annotations
import re

# Common English filler words that appear in many concept names and are not discriminative.
_STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "been", "they", "them",
    "were", "their", "more", "also", "when", "then", "than", "into", "over",
    "such", "each", "both", "some", "your", "what", "which", "about", "after",
    "topic", "concept", "method", "approach", "model", "based", "using",
}


def _terms(name: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", name.lower())
            if len(w) > 3 and w not in _STOPWORDS]


def _mentions(terms: list[str], text_lower: str) -> bool:
    return bool(terms) and any(t in text_lower for t in terms)


def refd_scores(concepts: list[dict], by_chunk: dict) -> dict:
    """{(prereq_slug, target_slug): score}. Positive => prereq_slug is a prerequisite of target_slug
    (target references prereq more than vice versa)."""
    chunks = [t.lower() for t in by_chunk.values()]
    terms = {c["slug"]: _terms(c.get("name", c["slug"])) for c in concepts}
    count = {s: sum(1 for ch in chunks if _mentions(terms[s], ch)) for s in terms}
    scores: dict = {}
    slugs = list(terms)
    for a in slugs:
        for b in slugs:
            if a == b:
                continue
            co = sum(1 for ch in chunks if _mentions(terms[a], ch) and _mentions(terms[b], ch))
            ref_a_to_b = co / count[a] if count[a] else 0.0
            ref_b_to_a = co / count[b] if count[b] else 0.0
            scores[(b, a)] = round(ref_a_to_b - ref_b_to_a, 4)   # prereq=b, target=a
    return scores
