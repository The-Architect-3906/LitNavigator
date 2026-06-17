from __future__ import annotations

import sqlite3

from litnav.state import NavState

# Short framing phrase per explanation strategy (deterministic; no LLM needed for teach).
_STRATEGY_FRAMING = {
    "direct": "Here is the core idea, stated directly:",
    "analogy": "Let me re-explain with an analogy:",
    "worked_example": "Let me walk through a concrete worked example:",
    "contrast_case": "Let me contrast it with what it is *not*:",
    "simpler_decomposition": "Let me break it into smaller pieces:",
}


def teach_node(state: NavState, conn: sqlite3.Connection) -> dict:
    concept_id = state["current_concept_id"]
    evidence = state.get("current_evidence") or []
    strategy = state.get("current_strategy") or "direct"
    depth = state.get("teach_depth") or "explain"
    reteach_count = state.get("reteach_count", {}).get(concept_id, 0)

    row = conn.execute("SELECT name FROM concepts WHERE id=?", (concept_id,)).fetchone()
    concept_name = row[0] if row else f"concept {concept_id}"

    # Reteach turns cite a different chunk than the first explanation when one is available.
    cited_chunks: list[str] = []
    if evidence:
        idx = min(reteach_count, len(evidence) - 1)
        chunk = evidence[idx]
        if depth == "recall":
            # Brief orientation (e.g. journalist intent): just the gist, one sentence.
            first = chunk["text"].split(". ")[0].strip()
            gist = (first if len(first) <= 240 else chunk["text"][:240].strip()).rstrip(".") + "."
            message = (f"**{concept_name}** (quick orientation)\n\n{gist}\n\n"
                       f"*(Source: chunk {chunk['chunk_id']})*")
        else:
            framing = _STRATEGY_FRAMING.get(strategy, _STRATEGY_FRAMING["direct"])
            message = (f"**{concept_name}** ({strategy})\n\n"
                       f"{framing}\n\n{chunk['text']}\n\n*(Source: chunk {chunk['chunk_id']})*")
        cited_chunks = [chunk["chunk_id"]]
    else:
        message = f"**{concept_name}** — no evidence found for this concept yet."

    return {
        "current_strategy": strategy,
        "current_cited_chunks": cited_chunks,
        "history": [{
            "event": "reteach" if reteach_count > 0 else "teach",
            "concept_id": concept_id, "strategy": strategy, "depth": depth,
            "cited_chunks": cited_chunks, "message": message,
        }],
    }
