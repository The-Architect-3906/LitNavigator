"""induce_scaffold — literature-induced scaffolding (M3, the core novelty).

For an off-skeleton concept (one the user asks about that is NOT in the curated DAG),
read already-ingested chunks, induce a prerequisite edge into an existing concept, mine
a field misconception, label the frontier status, and slot it into the route. It also
adopts the supporting chunks and a quiz item for the induced concept so the normal
retrieve -> teach -> check -> grade inner loop can teach it.

Provenance is explicit (source='induced'), and confidence is computed by a transparent
rule — never emitted by the LLM. Offline (provider=none) the evidence strength comes from
the offline-prerun candidate; with provider=qwen the LLM labels strength over the real
chunk text (candidate label is the fallback). induced_confidence() always computes the number.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.state import NavState, initial_concept_state
from litnav.storage import repo

_STRENGTH_BONUS = {"weak_hint": 0.05, "general_statement": 0.15, "explicit_assertion": 0.25}
_VALID_STRENGTH = set(_STRENGTH_BONUS)


def induced_confidence(n_chunks: int, max_strength: str, multi_paper: bool) -> float:
    """Canonical, transparent confidence rule (byte-identical to spec §5.3 / data-contract).
    The LLM may pick chunks and label strength, but never returns this number."""
    strength_bonus = _STRENGTH_BONUS[max_strength]
    multi_paper_bonus = 0.10 if multi_paper else 0.0
    return round(min(0.95, 0.35 + 0.15 * n_chunks + strength_bonus + multi_paper_bonus), 2)


def _chunk_texts(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[str]:
    texts = []
    for cid in chunk_ids:
        row = conn.execute("SELECT text FROM paper_chunks WHERE id=?", (cid,)).fetchone()
        if row:
            texts.append(row[0])
    return texts


def _label_strength(conn: sqlite3.Connection, chunk_ids: list[str], fallback: str) -> str:
    """LLM seam: with a provider set, label evidence strength over the real chunk text;
    offline (provider=none) complete_json returns the fallback unchanged."""
    prompt = (
        "Rate how strongly the evidence asserts the claim it is cited for.\n"
        f"Evidence: {_chunk_texts(conn, chunk_ids)}\n"
        'Respond as JSON: {"max_strength": "weak_hint" | "general_statement" | "explicit_assertion"}'
    )
    result = llm_client.complete_json(prompt, fallback={"max_strength": fallback})
    labelled = result.get("max_strength", fallback)
    return labelled if labelled in _VALID_STRENGTH else fallback


def _extract_misconception(conn: sqlite3.Connection, chunk_ids: list[str], concept_name: str,
                           fallback: dict) -> dict:
    """Autonomous live induction (F): with a provider set, the LLM READS the real chunk text
    and PROPOSES the misconception (wrong vs correct model) plus its evidence strength — not
    just a strength label. Offline / on any malformed field, the prepared candidate is the
    fallback, so this stays deterministic with provider=none. Confidence is never taken from
    the LLM; the caller computes it via induced_confidence().
    """
    prompt = (
        f"Reading the evidence below about \"{concept_name}\", identify ONE common misconception a "
        "learner might hold and the correct model that corrects it. Ground both ONLY in the evidence.\n\n"
        f"Evidence: {_chunk_texts(conn, chunk_ids)}\n\n"
        'Respond as JSON: {"wrong_model": "<short wrong belief>", '
        '"correct_model": "<short correction>", '
        '"max_strength": "weak_hint" | "general_statement" | "explicit_assertion"}'
    )
    result = llm_client.complete_json(prompt, fallback={})
    wrong = result.get("wrong_model")
    correct = result.get("correct_model")
    strength = result.get("max_strength")
    return {
        "wrong_model": wrong if isinstance(wrong, str) and wrong.strip() else fallback["wrong_model"],
        "correct_model": correct if isinstance(correct, str) and correct.strip() else fallback["correct_model"],
        "max_strength": strength if strength in _VALID_STRENGTH else fallback["max_strength"],
    }


def induce_scaffold_node(state: NavState, conn: sqlite3.Connection,
                         candidate: dict | None = None) -> dict:
    candidate = candidate or state.get("pending_induction")
    if not candidate:
        raise ValueError("induce_scaffold_node requires a candidate (state['pending_induction'])")

    session_id = state["session_id"]
    route_version = state["route_version"]

    off = candidate["off_skeleton"]
    prereq = repo.get_concept_by_slug(conn, candidate["prereq_slug"])
    if prereq is None:
        raise ValueError(f"prereq concept {candidate['prereq_slug']!r} not found in curated graph")

    # 1) Create the induced concept (off the curated skeleton).
    new_id = repo.next_concept_id(conn)
    repo.create_concept(conn, new_id, off["slug"], off["name"], off.get("frontier_flag"))

    # 2) Induced prerequisite edge — confidence rule-computed from (LLM- or fixture-) labelled strength.
    e = candidate["edge"]
    edge_chunks = e["evidence_chunks"]
    edge_strength = _label_strength(conn, edge_chunks, e["max_strength"])
    edge_conf = induced_confidence(len(edge_chunks), edge_strength, e.get("multi_paper", False))
    repo.record_induced_edge(conn, prereq["id"], new_id, edge_conf, edge_chunks)
    edge_basis = {"n_chunks": len(edge_chunks), "max_strength": edge_strength,
                  "multi_paper": e.get("multi_paper", False)}
    repo.record_induction_log(
        conn, session_id, "prereq",
        output={"prereq": candidate["prereq_slug"], "target": off["slug"], "confidence": edge_conf},
        evidence_chunks=edge_chunks, confidence=edge_conf, confidence_basis=edge_basis,
    )

    # 3) Mined misconception — LLM proposes wrong/correct model from the real chunks (F);
    #    the prepared candidate is the offline fallback. Confidence stays rule-computed.
    m = candidate["misconception"]
    m_chunks = m["evidence_chunks"]
    extracted = _extract_misconception(conn, m_chunks, off["name"], m)
    m_strength = extracted["max_strength"]
    m_conf = induced_confidence(len(m_chunks), m_strength, m.get("multi_paper", False))
    repo.record_induced_misconception(
        conn, m["id"], new_id, extracted["wrong_model"], extracted["correct_model"], m_conf,
        m_chunks[0] if m_chunks else None, detect_hint=m.get("detect_hint"),
        reteach_strategy=m.get("reteach_strategy", "analogy"),
    )
    m_basis = {"n_chunks": len(m_chunks), "max_strength": m_strength,
               "multi_paper": m.get("multi_paper", False)}
    repo.record_induction_log(
        conn, session_id, "misconception",
        output={"id": m["id"], "concept": off["slug"], "confidence": m_conf},
        evidence_chunks=m_chunks, confidence=m_conf, confidence_basis=m_basis,
    )

    # 4) Make the induced concept teachable by the normal inner loop:
    #    adopt its supporting chunks (so retrieve finds them) and add a quiz item.
    for cid in dict.fromkeys(edge_chunks + m_chunks):  # de-duped, ordered
        repo.assign_chunk_concept(conn, cid, new_id)
    q = candidate.get("quiz")
    if q:
        repo.create_quiz_item(
            conn, new_id, q["question"], q["answer_key"],
            evidence_chunk_id=edge_chunks[0] if edge_chunks else None,
            source_paper_id=repo.get_chunk_paper_id(conn, edge_chunks[0]) if edge_chunks else None,
            qtype=q.get("qtype", "explain"), difficulty=q.get("difficulty", 1),
            targets_misconception=m["id"],
        )

    # 5) Learner state for the induced concept (planner ran before it existed).
    learner_state = dict(state.get("learner_state", {}))
    learner_state[new_id] = initial_concept_state()
    repo.upsert_learner_state(conn, session_id, new_id, mastery=0.4, confidence=0.0, n_observations=0)

    # 6) Slot the induced concept into the route and record the decision.
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

    # 7) Make the induced prereq edge visible to the router. planner built concept_dag before
    #    this concept existed, so without this the induced prereq is dead for routing — a failed
    #    induced concept could never diagnose/replan to its prereq the way a curated one does.
    concept_dag = {k: list(v) for k, v in state.get("concept_dag", {}).items()}
    concept_dag.setdefault(new_id, []).append(prereq["id"])

    return {
        "route": route,
        "learner_state": learner_state,
        "concept_dag": concept_dag,
        "current_concept_id": new_id,
        "rationale": rationale,
        "history": [{"event": "induce_scaffold", "concept_id": new_id, "slug": off["slug"],
                     "edge_confidence": edge_conf, "misconception_confidence": m_conf}],
    }
