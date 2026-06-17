from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.state import NavState

# Short framing phrase per explanation strategy (deterministic fallback; no LLM needed).
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

    cited_chunks: list[str] = []
    teach_token_cost = 0
    if evidence:
        idx = min(reteach_count, len(evidence) - 1)
        chunk = evidence[idx]
        cited_chunks = [chunk["chunk_id"]]

        # Deterministic body (offline fallback).
        if depth == "recall":
            first = chunk["text"].split(". ")[0].strip()
            det_body = (first if len(first) <= 240 else chunk["text"][:240].strip()).rstrip(".") + "."
            header = f"**{concept_name}** (quick orientation)"
        else:
            det_body = f"{_STRATEGY_FRAMING.get(strategy, _STRATEGY_FRAMING['direct'])}\n\n{chunk['text']}"
            header = f"**{concept_name}** ({strategy})"

        # LLM grounded explanation when a provider is configured; offline returns det_body unchanged.
        length = "in one short sentence (a quick orientation)" if depth == "recall" else "in 2-4 sentences"
        prompt = (
            f"You are a patient tutor. Teach the concept \"{concept_name}\" using a {strategy} "
            f"explanation, {length}. Ground it ONLY in the evidence below — do not add facts beyond it.\n\n"
            f"Evidence:\n{chunk['text']}"
        )
        body = llm_client.complete_text(prompt, fallback=det_body,
                                        max_tokens=80 if depth == "recall" else 300)
        teach_token_cost = llm_client.last_token_cost()

        message = f"{header}\n\n{body}\n\n*(Source: chunk {chunk['chunk_id']})*"
    else:
        message = f"**{concept_name}** — no evidence found for this concept yet."

    return {
        "current_strategy": strategy,
        "current_cited_chunks": cited_chunks,
        "teach_token_cost": teach_token_cost,
        "history": [{
            "event": "reteach" if reteach_count > 0 else "teach",
            "concept_id": concept_id, "strategy": strategy, "depth": depth,
            "cited_chunks": cited_chunks, "message": message,
        }],
    }
