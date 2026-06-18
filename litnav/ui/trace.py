"""Build a judge-facing trace for a session from the SQLite domain tables.

Pure data — no HTTP, no rendering — so it is trivially testable and reused by the
FastAPI panel, the CLI debug runner, and tests.
"""
from __future__ import annotations

import json
import sqlite3


def _loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def build_trace(conn: sqlite3.Connection, session_id: str) -> dict:
    sess_row = conn.execute(
        "SELECT id, topic, status FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    session = {"id": sess_row[0], "topic": sess_row[1], "status": sess_row[2]} if sess_row else {}

    ver_row = conn.execute(
        "SELECT MAX(route_version) FROM route_steps WHERE session_id=?", (session_id,)
    ).fetchone()
    route_version = ver_row[0] if ver_row and ver_row[0] is not None else 1

    route = [
        {"step_id": r[0], "concept_id": r[1], "name": r[2], "status": r[3], "reason": r[4]}
        for r in conn.execute(
            "SELECT rs.step_id, rs.concept_id, c.name, rs.status, rs.reason "
            "FROM route_steps rs LEFT JOIN concepts c ON c.id = rs.concept_id "
            "WHERE rs.session_id=? AND rs.route_version=? ORDER BY rs.rowid",
            (session_id, route_version),
        ).fetchall()
    ]

    # Induced (machine-derived) prerequisite edges — kept distinct from curated for the panel.
    induced_edges = [
        {"prereq_id": r[0], "prereq": r[1], "target_id": r[2], "target": r[3],
         "confidence": r[4], "evidence": _loads(r[5], [])}
        for r in conn.execute(
            "SELECT e.prereq_concept, p.name, e.target_concept, t.name, e.confidence, e.evidence "
            "FROM concept_edges e "
            "LEFT JOIN concepts p ON p.id = e.prereq_concept "
            "LEFT JOIN concepts t ON t.id = e.target_concept "
            "WHERE e.source='induced'",
        ).fetchall()
    ]
    induced_target_ids = {e["target_id"] for e in induced_edges}

    ls_rows = conn.execute(
        "SELECT ls.concept_id, c.name, c.slug, c.frontier_flag, ls.mastery, ls.confidence, "
        "ls.n_observations, ls.held_misconceptions, ls.tried_strategies "
        "FROM learner_state ls LEFT JOIN concepts c ON c.id = ls.concept_id "
        "WHERE ls.session_id=? ORDER BY ls.concept_id",
        (session_id,),
    ).fetchall()
    concepts = [
        {"concept_id": r[0], "name": r[1], "slug": r[2], "frontier_flag": r[3] or "consensus",
         "mastery": round(r[4], 3), "confidence": round(r[5], 3), "n_observations": r[6],
         "held_misconceptions": _loads(r[7], []), "tried_strategies": _loads(r[8], []),
         "induced": r[0] in induced_target_ids}
        for r in ls_rows
    ]

    decisions = [
        {"route_version": r[0], "from_node": r[1], "decision": r[2],
         "rationale": r[3], "token_cost": r[4], "state_snapshot": _loads(r[5], {})}
        for r in conn.execute(
            "SELECT route_version, from_node, decision, rationale, token_cost, state_snapshot "
            "FROM decisions WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    ]

    tutor_turns = [
        {"concept_id": r[0], "name": r[1], "turn_type": r[2], "strategy": r[3],
         "pre_check_score": r[4], "post_check_score": r[5],
         "cited_chunks": _loads(r[6], []), "token_cost": r[7],
         "mastery_after": round(r[8], 3) if r[8] is not None else None,
         "confidence_after": round(r[9], 3) if r[9] is not None else None}
        for r in conn.execute(
            "SELECT tt.concept_id, c.name, tt.turn_type, tt.strategy, tt.pre_check_score, "
            "tt.post_check_score, tt.cited_chunks, tt.token_cost, tt.mastery_after, "
            "tt.confidence_after "
            "FROM tutor_turns tt LEFT JOIN concepts c ON c.id = tt.concept_id "
            "WHERE tt.session_id=? ORDER BY tt.id",
            (session_id,),
        ).fetchall()
    ]

    induction = [
        {"kind": r[0], "output": _loads(r[1], {}), "evidence_chunks": _loads(r[2], []),
         "confidence": r[3], "confidence_basis": _loads(r[4], {})}
        for r in conn.execute(
            "SELECT kind, output, evidence_chunks, confidence, confidence_basis "
            "FROM induction_log WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    ]

    # Per-turn learner answers, in graph order — paired 1:1 with tutor_turns
    # (grade_node writes one quiz_attempt and one tutor_turn per check).
    attempts = [
        {"answer": r[0], "score": r[1], "detected_misconception": r[2]}
        for r in conn.execute(
            "SELECT user_answer, score, detected_misconception FROM quiz_attempts "
            "WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    ]

    # A single chronological view the CLI and panel can both render. Walk the decisions in
    # order: a ROUTING decision pairs with the next quizzed tutor_turn (1:1, in order); a
    # 'lecture' decision is a quizless orientation turn (no tutor_turn / no answer / no
    # mastery). 'induce' is pre-loop and shown in the induced/induction sections, not here.
    _ROUTING = ("advance", "reteach", "diagnose", "replan", "concede")
    names = {c["concept_id"]: c["name"] for c in concepts}
    timeline = []
    j = 0
    for d in decisions:
        if d["decision"] in _ROUTING:
            tt = tutor_turns[j] if j < len(tutor_turns) else {}
            att = attempts[j] if j < len(attempts) else {}
            j += 1
            timeline.append({
                "index": len(timeline) + 1,
                "name": tt.get("name"), "turn_type": tt.get("turn_type"), "strategy": tt.get("strategy"),
                "cited_chunks": tt.get("cited_chunks", []),
                "answer": att.get("answer"), "score": att.get("score"),
                "detected_misconception": att.get("detected_misconception"),
                "mastery_after": tt.get("mastery_after"), "confidence_after": tt.get("confidence_after"),
                "decision": d["decision"], "rationale": d["rationale"],
            })
        elif d["decision"] == "lecture":
            timeline.append({
                "index": len(timeline) + 1,
                "name": names.get(d["state_snapshot"].get("concept_id")),
                "turn_type": "lecture", "strategy": None, "cited_chunks": [],
                "answer": None, "score": None, "detected_misconception": None,
                "mastery_after": None, "confidence_after": None,
                "decision": "lecture", "rationale": d["rationale"],
            })

    cited_ids: list[str] = []
    for tt in tutor_turns:
        for cid in tt["cited_chunks"]:
            if cid not in cited_ids:
                cited_ids.append(cid)
    for ind in induction:  # induced scaffolding cites chunks too
        for cid in ind["evidence_chunks"]:
            if cid not in cited_ids:
                cited_ids.append(cid)
    evidence = []
    for cid in cited_ids:
        row = conn.execute(
            "SELECT id, paper_id, text FROM paper_chunks WHERE id=?", (cid,)
        ).fetchone()
        if row:
            evidence.append({"chunk_id": row[0], "paper_id": row[1], "text": row[2]})

    total_tokens = sum((t["token_cost"] or 0) for t in tutor_turns) + \
        sum((d["token_cost"] or 0) for d in decisions)

    return {
        "session": session,
        "route_version": route_version,
        "route": route,
        "concepts": concepts,
        "decisions": decisions,
        "tutor_turns": tutor_turns,
        "timeline": timeline,
        "evidence": evidence,
        "induced_edges": induced_edges,
        "induction": induction,
        "total_token_cost": total_tokens,
    }
