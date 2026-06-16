"""induce_scaffold — literature-induced scaffolding (M3, the core novelty).

For an off-skeleton concept (one the user asks about that is NOT in the curated DAG),
read already-ingested chunks, induce a prerequisite edge into an existing concept, mine
a field misconception, label the frontier status, and slot it into the route. Provenance
is explicit (source='induced'), and confidence is computed by a transparent rule — never
emitted by the LLM.

Offline (provider=none) it replays the offline-prerun candidate from the fixture; with
provider=qwen the LLM would extract the supporting chunks and label each one's language
strength over the real text. Either way induced_confidence() computes the number.
"""
from __future__ import annotations

import sqlite3

from litnav.state import NavState
from litnav.storage import repo

_STRENGTH_BONUS = {"weak_hint": 0.05, "general_statement": 0.15, "explicit_assertion": 0.25}


def induced_confidence(n_chunks: int, max_strength: str, multi_paper: bool) -> float:
    """Canonical, transparent confidence rule (byte-identical to spec §5.3 / data-contract).
    The LLM may pick chunks and label strength, but never returns this number."""
    strength_bonus = _STRENGTH_BONUS[max_strength]
    multi_paper_bonus = 0.10 if multi_paper else 0.0
    return round(min(0.95, 0.35 + 0.15 * n_chunks + strength_bonus + multi_paper_bonus), 2)


def induce_scaffold_node(state: NavState, conn: sqlite3.Connection, candidate: dict) -> dict:
    session_id = state["session_id"]
    route_version = state["route_version"]

    off = candidate["off_skeleton"]
    prereq = repo.get_concept_by_slug(conn, candidate["prereq_slug"])
    if prereq is None:
        raise ValueError(f"prereq concept {candidate['prereq_slug']!r} not found in curated graph")

    # 1) Create the induced concept (off the curated skeleton).
    new_id = repo.next_concept_id(conn)
    repo.create_concept(conn, new_id, off["slug"], off["name"], off.get("frontier_flag"))

    # 2) Induced prerequisite edge — confidence is rule-computed from the evidence.
    e = candidate["edge"]
    edge_chunks = e["evidence_chunks"]
    edge_conf = induced_confidence(len(edge_chunks), e["max_strength"], e.get("multi_paper", False))
    repo.record_induced_edge(conn, prereq["id"], new_id, edge_conf, edge_chunks)
    edge_basis = {"n_chunks": len(edge_chunks), "max_strength": e["max_strength"],
                  "multi_paper": e.get("multi_paper", False)}
    repo.record_induction_log(
        conn, session_id, "prereq",
        output={"prereq": candidate["prereq_slug"], "target": off["slug"], "confidence": edge_conf},
        evidence_chunks=edge_chunks, confidence=edge_conf, confidence_basis=edge_basis,
    )

    # 3) Mined misconception — also rule-computed confidence, cited to a chunk.
    m = candidate["misconception"]
    m_chunks = m["evidence_chunks"]
    m_conf = induced_confidence(len(m_chunks), m["max_strength"], m.get("multi_paper", False))
    repo.record_induced_misconception(
        conn, m["id"], new_id, m["wrong_model"], m["correct_model"], m_conf,
        m_chunks[0] if m_chunks else None,
    )
    m_basis = {"n_chunks": len(m_chunks), "max_strength": m["max_strength"],
               "multi_paper": m.get("multi_paper", False)}
    repo.record_induction_log(
        conn, session_id, "misconception",
        output={"id": m["id"], "concept": off["slug"], "confidence": m_conf},
        evidence_chunks=m_chunks, confidence=m_conf, confidence_basis=m_basis,
    )

    # 4) Slot the induced concept into the route and record the decision.
    route = [dict(s) for s in state.get("route", [])]
    new_step = {
        "step_id": f"route-induced-{new_id:03d}",
        "concept_id": new_id,
        "paper_id": None,
        "reason": f"Induced off-skeleton concept '{off['slug']}'; prereq {candidate['prereq_slug']} "
                  f"(induced edge, conf {edge_conf}).",
        "status": "pending",
        "confidence": edge_conf,
    }
    route.append(new_step)
    repo.write_route_steps(conn, session_id, route_version, [new_step])

    rationale = (
        f"'{off['slug']}' is off the curated skeleton. Induced prereq "
        f"{candidate['prereq_slug']} -> {off['slug']} (conf {edge_conf}, source=induced) and mined "
        f"misconception '{m['id']}' (conf {m_conf}), both cited to chunks; taught as "
        f"{off.get('frontier_flag')}. You can overrule either."
    )
    repo.record_decision(
        conn, session_id, route_version, "induce_scaffold", "induce", rationale,
        state_snapshot={"induced_concept_id": new_id, "edge_confidence": edge_conf,
                        "misconception_confidence": m_conf},
    )

    return {
        "route": route,
        "current_concept_id": new_id,
        "rationale": rationale,
        "history": [{"event": "induce_scaffold", "concept_id": new_id, "slug": off["slug"],
                     "edge_confidence": edge_conf, "misconception_confidence": m_conf}],
    }
