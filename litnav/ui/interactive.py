"""Interactive tutor session — real human-in-the-loop over the LangGraph tutor.

The graph runs with `interrupt_after=["check"]`, so it teaches a concept, presents a quiz,
and *pauses*. The user submits a real answer; we inject it and resume (grade -> route ->
teach -> check -> pause again) until the route finishes. This reuses the SqliteSaver
checkpoint/interrupt proven in M1. Teaching is deterministic today; swap Qwen into `teach`
later without changing this loop.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage import repo
from litnav.ui.cost import session_cost


class TutorSession:
    def __init__(self, domain_conn: sqlite3.Connection, checkpoint_conn: sqlite3.Connection,
                 session_id: str):
        self.conn = domain_conn
        self.sid = session_id
        self.app = build_graph(domain_conn, checkpoint_conn, interrupt_after=["check"])
        self.config = {"configurable": {"thread_id": session_id}, "recursion_limit": 200}

    def start(self, topic: str, target_concept_ids: Optional[List[int]] = None,
              intent: Optional[str] = None, pending_induction: Optional[dict] = None,
              mastery_threshold: float = 0.8) -> dict:
        state = make_initial_state(
            self.sid, topic, target_concept_ids or [],
            intent=intent, pending_induction=pending_induction,
            mastery_threshold=mastery_threshold,
        )
        self.app.invoke(state, self.config)
        return self.current()

    def answer(self, text: str) -> dict:
        # Inject the learner's real answer and resume from the post-check interrupt.
        self.app.update_state(self.config, {"user_answer": text, "pending_answers": []})
        self.app.invoke(None, self.config)
        return self.current()

    _STEP_LABELS = {
        "planner": "Planning the route",
        "induce": "Inducing scaffold from the papers",
        "select_next": "Selecting the next concept",
        "retrieve": "Retrieving evidence",
        "teach": "Teaching (grounded in evidence)",
        "check": "Posing a quiz",
        "grade": "Grading your answer",
        "diagnose": "Diagnosing a missing prerequisite",
        "replan": "Re-planning the route",
        "advance": "Advancing",
        "reteach": "Re-teaching with a new strategy",
        "concede": "Conceding honestly",
    }

    def _step_event(self, node: str, delta: dict) -> dict:
        detail = ""
        if node == "retrieve":
            detail = f"{len(delta.get('current_evidence') or [])} chunks"
        elif node in ("teach", "reteach"):
            detail = delta.get("current_strategy") or ""
        elif node == "grade":
            qr = delta.get("quiz_result") or {}
            detail = "correct" if qr.get("score") == 1.0 else "wrong"
            if qr.get("detected_misconception"):
                detail += f" · {qr['detected_misconception']}"
        elif node == "induce":
            detail = "source=induced"
        return {"type": "step", "node": node,
                "label": self._STEP_LABELS.get(node, node), "detail": detail}

    def _terminal_events(self) -> list[dict]:
        cur = self.current()
        return [
            {"type": "teach", "text": cur.get("teach") or "", "cited": cur.get("cited") or []},
            {"type": "question", "text": cur.get("question") or ""},
            {"type": "state", "route": cur["route"], "route_version": cur["route_version"],
             "learner": cur["learner"], "cited": cur["cited"], "decision": cur["decision"],
             "rationale": cur["rationale"], "induced": cur["induced"], "intent": cur.get("intent"),
             "cost": session_cost(self.conn, self.sid)},
            {"type": "done", "done": cur["done"], "mastery": cur.get("mastery"),
             "confidence": cur.get("confidence")},
        ]

    def stream_answer(self, text: str):
        """Inject the answer and resume, yielding one event per executed node, then the
        terminal teach/question/state/done events. Used by the SSE endpoint."""
        self.app.update_state(self.config, {"user_answer": text, "pending_answers": []})
        for update in self.app.stream(None, self.config, stream_mode="updates"):
            for node, delta in update.items():
                yield self._step_event(node, delta or {})
        for ev in self._terminal_events():
            yield ev

    def current(self) -> dict:
        snap = self.app.get_state(self.config)
        vals = snap.values
        done = not snap.next  # no next node queued -> the route finished

        teach_msg = None
        for ev in reversed(vals.get("history", [])):
            if ev.get("event") in ("teach", "reteach") and ev.get("message"):
                teach_msg = ev["message"]
                break

        quiz = vals.get("current_quiz_item") or {}
        last = vals.get("quiz_result") or {}

        # When the route finishes, current_concept_id is cleared — fall back to the last
        # graded concept so we can still report its mastery/confidence.
        concept_id = vals.get("current_concept_id")
        focus_id = concept_id if concept_id is not None else last.get("concept_id")
        name = None
        if focus_id is not None:
            row = self.conn.execute("SELECT name FROM concepts WHERE id=?", (focus_id,)).fetchone()
            name = row[0] if row else None

        cs = (vals.get("learner_state") or {}).get(focus_id, {}) if focus_id is not None else {}

        return {
            "session_id": self.sid,
            "done": done,
            "concept_id": concept_id,
            "concept_name": name,
            "teach": teach_msg,
            "question": (quiz.get("question") if not done else None),
            "mastery": round(cs.get("mastery", 0.0), 3) if cs else None,
            "confidence": round(cs.get("confidence", 0.0), 3) if cs else None,
            "last_feedback": last.get("feedback"),
            "last_detected_misconception": last.get("detected_misconception"),
            "route_version": vals.get("route_version"),
            "route": [
                {"concept_id": st.get("concept_id"),
                 "name": (self.conn.execute("SELECT name FROM concepts WHERE id=?",
                                            (st.get("concept_id"),)).fetchone() or [None])[0],
                 "status": st.get("status")}
                for st in (vals.get("route") or [])
            ],
            "evidence": vals.get("current_evidence") or [],
            "cited": [
                {"chunk_id": cid,
                 "text": (self.conn.execute("SELECT text FROM paper_chunks WHERE id=?", (cid,)).fetchone() or [""])[0],
                 "paper_id": (self.conn.execute("SELECT paper_id FROM paper_chunks WHERE id=?", (cid,)).fetchone() or [None])[0]}
                for cid in (vals.get("current_cited_chunks") or [])
            ],
            "decision": vals.get("decision"),
            "rationale": vals.get("rationale"),
            "learner": [
                {"name": (self.conn.execute("SELECT name FROM concepts WHERE id=?", (cid,)).fetchone() or [None])[0],
                 "mastery": round(cs.get("mastery", 0.0), 3),
                 "confidence": round(cs.get("confidence", 0.0), 3),
                 "held": cs.get("held_misconceptions", [])}
                for cid, cs in (vals.get("learner_state") or {}).items()
                if cs.get("n_observations")
            ],
            "induced": [
                {"prereq": (self.conn.execute("SELECT name FROM concepts WHERE id=?", (e["prereq_concept"],)).fetchone() or [None])[0],
                 "target": (self.conn.execute("SELECT name FROM concepts WHERE id=?", (e["target_concept"],)).fetchone() or [None])[0],
                 "confidence": e["confidence"]}
                for e in repo.get_induced_edges(self.conn)
            ],
            "intent": vals.get("intent"),
            "teach_depth": vals.get("teach_depth"),
            "mastery_threshold": vals.get("mastery_threshold"),
        }
