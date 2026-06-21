"""Source-relevance gate: drop off-topic sources after ranking, before full-text fetch.

Uses a cheap LLM call to filter sources that are about a different field, a film, or an
unrelated subject. Never starves digest -- always keeps at least min_keep sources.
Falls back to passthrough when offline (provider=none/offline).
"""
from __future__ import annotations
import os
import sqlite3

from litnav.discover.contract import Source
from litnav.llm import router


def relevance_gate(
    search_query: str,
    sources: list[Source],
    *,
    conn: sqlite3.Connection | None = None,
    session_id: str | None = None,
    budget: int | None = None,
    min_keep: int = 2,
) -> list[Source]:
    """Filter sources to those genuinely on-topic for search_query.

    Returns:
        A list of Source objects in the same rank order as the input, with off-topic
        sources removed. If fewer than min_keep remain, falls back to the top min_keep
        by original rank order. Empty input is returned unchanged. Offline/none provider
        returns sources unchanged (deterministic passthrough).
    """
    if not sources:
        return sources

    if os.environ.get("LITNAV_LLM_PROVIDER", "").lower() in ("none", "offline"):
        return sources

    listing = "\n".join(
        f"{i}: {s.title} — {s.abstract[:300]}" for i, s in enumerate(sources)
    )

    prompt = (
        "Which of these sources are genuinely about the topic below? "
        "A source about a different field, a film, or an unrelated subject is NOT relevant. "
        f"Topic: {search_query}\n\n"
        f"Sources:\n{listing}\n\n"
        'Respond JSON only: {"relevant_indices": [<indices that are on-topic>]}'
    )

    fallback = {"relevant_indices": list(range(len(sources)))}
    res = router.complete_json(
        prompt,
        tier="cheap",
        stage="discover",
        fallback=fallback,
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    raw_idxs = res.get("relevant_indices") if isinstance(res, dict) else None
    if not isinstance(raw_idxs, list):
        raw_idxs = list(range(len(sources)))

    # Keep only valid integer indices in range; preserve INPUT rank order by iterating sources
    valid_idx_set = {i for i in raw_idxs if isinstance(i, int) and 0 <= i < len(sources)}
    kept = [s for i, s in enumerate(sources) if i in valid_idx_set]

    if len(kept) < min_keep:
        # Never starve digest -- fall back to top min_keep by original rank
        return sources[:min_keep]

    return kept
