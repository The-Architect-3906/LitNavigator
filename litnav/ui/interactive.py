"""Interactive tutor session — real human-in-the-loop over the LangGraph tutor.

The graph runs with `interrupt_after=["check", "assess_next"]`, so it can pause at either
the legacy concept quiz or the new keypoint-based adaptive quiz. The user submits a real
answer; we inject it and resume until the route finishes. This reuses the SqliteSaver
checkpoint/interrupt proven in M1.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from litnav.conversation import dispatch, _looks_learn_request
from litnav.graph.builder import build_graph, make_initial_state
from litnav.nodes.retrieve import retrieve_node
from litnav.recommend.recommend_next import recommend_next
from litnav.storage import repo
from litnav.ui.cost import session_cost
from litnav.ui.flow_meta import meta_for
from litnav.ui.graph_svg import to_svg
from litnav.ui.trace import concept_graph
# Open-world cold-start (live mode): discover real sources → digest into a graph → teach.
from litnav.discover import find_sources
from litnav.discover.contract import DiscoverInput
from litnav.digest import pipeline
from litnav.digest.contract import DigestInput, SourceDoc


class TutorSession:
    _TERMINAL_ROUTE_STATUSES = {"done", "conceded", "lectured"}

    def __init__(self, domain_conn: sqlite3.Connection, checkpoint_conn: sqlite3.Connection,
                 session_id: str, out_dir: str = "artifacts"):
        self.conn = domain_conn
        self.sid = session_id
        self.app = build_graph(domain_conn, checkpoint_conn,
                               interrupt_after=["check", "assess_next", "review_probe"])
        self.config = {"configurable": {"thread_id": session_id}, "recursion_limit": 200}
        self.out_dir = out_dir
        self.artifact_path: str | None = None
        self._artifact_made = False

    def start(self, topic: str, target_concept_ids: Optional[List[int]] = None,
              intent: Optional[str] = None, pending_induction: Optional[dict] = None,
              mastery_threshold: float = 0.8, goal_text: Optional[str] = None) -> dict:
        state = make_initial_state(
            self.sid, topic, target_concept_ids or [],
            intent=intent, pending_induction=pending_induction,
            mastery_threshold=mastery_threshold, goal_text=goal_text,
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
        # Legacy path
        "teach": "Teaching (grounded in evidence)",
        "check": "Posing a quiz",
        "grade": "Grading your answer",
        "diagnose": "Diagnosing a missing prerequisite",
        "replan": "Re-planning the route",
        "advance": "Advancing",
        "reteach": "Re-teaching with a new strategy",
        "concede": "Conceding honestly",
        # TEACH/ASSESS path
        "init_kp": "Initializing keypoint progress",
        "teach_kp": "Teaching key point",
        "assess_next": "Posing adaptive quiz",
        "grade_kp": "Grading against rubric",
        "reteach_kp": "Re-teaching key point with new strategy",
        "advance_kp": "Checking advance criteria",
        # ORIENT + LOST
        "orient_tour": "Walking the concept roadmap",
        "handle_lost": "Re-explaining from a different angle",
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
        meta = meta_for(node)
        return {"type": "step", "node": node,
                "label": self._STEP_LABELS.get(node, node), "detail": detail,
                "skill": meta["skill"], "method": meta["method"], "paper": meta["paper"]}

    def _recommend(self) -> list[dict]:
        """Call recommend_next and return a serialisable list; empty on any error."""
        try:
            recs = recommend_next(self.conn, self.sid)
            return [
                {"concept_id": r.concept_id, "name": r.name,
                 "reason": r.reason, "eligible": r.eligible, "score": r.score}
                for r in recs
            ]
        except Exception:
            return []

    def _artifact_event(self) -> Optional[dict]:
        """Generate the take-away once, when the route is complete. Returns an artifact event
        (with a download URL + preview) or None. Idempotent via self._artifact_made."""
        cur = self.current()
        if not cur.get("done") or self._artifact_made:
            return None
        tids = [st["concept_id"] for st in cur["route"] if st.get("concept_id") is not None]
        if not tids:
            return None
        from litnav.artifact.contract import ArtifactInput
        from litnav.artifact.make_artifact import make_artifact
        from litnav.llm import lang as lang_mod
        teach_blob = " ".join(cur.get("teach_messages") or []) or "x"
        language = lang_mod.detect_language(teach_blob)
        try:
            res = make_artifact(ArtifactInput(tids, {}, language=language),
                                conn=self.conn, session_id=self.sid, out_dir=f"{self.out_dir}/{self.sid}")
        except Exception:
            return None
        self._artifact_made = True
        self.artifact_path = res.artifact_path
        body = ""
        try:
            from pathlib import Path as _P
            body = _P(res.artifact_path).read_text(encoding="utf-8")
        except Exception:
            pass
        return {"type": "artifact", "format": res.format, "url": f"/tutor/{self.sid}/artifact",
                "citations": res.citations, "preview": body[:600]}

    def _terminal_events(self) -> list[dict]:
        cur = self.current()
        events = [
            {"type": "teach", "text": text, "cited": cur.get("cited") or []}
            for text in (cur.get("teach_messages") or [])
            if text
        ]
        events.extend([
            {"type": "question", "text": cur.get("question") or "", "bloom_level": cur.get("bloom")},
            {"type": "state", "route": cur["route"], "route_version": cur["route_version"],
             "learner": cur["learner"], "cited": cur["cited"], "decision": cur["decision"],
             "rationale": cur["rationale"], "induced": cur["induced"], "intent": cur.get("intent"),
             "graph": to_svg(concept_graph(self.conn, self.sid)),
             "cost": session_cost(self.conn, self.sid),
             "recommend": self._recommend()},
        ])
        art = self._artifact_event()
        if art:
            events.append(art)
        events.append({"type": "done", "done": cur["done"], "mastery": cur.get("mastery"),
                       "confidence": cur.get("confidence")})
        return events

    @staticmethod
    def _recent_teach_messages(history: list[dict]) -> list[str]:
        """Return the teach/reteach block that most recently led to the current question."""
        if not history:
            return []

        teach_events = {"teach", "reteach", "teach_kp", "reteach_kp", "orient_tour", "handle_lost"}
        # "lecture" marks the end of a no-quiz concept — treat it as a boundary so
        # we still find the preceding "teach" event and surface its content.
        boundary_events = {"assess_next", "check", "lecture"}

        idx = len(history) - 1
        if history[idx].get("event") in boundary_events:
            idx -= 1

        collected: list[str] = []
        while idx >= 0 and history[idx].get("event") in teach_events:
            text = history[idx].get("message") or history[idx].get("text") or ""
            closing = history[idx].get("closing") or ""
            if text:
                collected.append(text + closing)
            idx -= 1
        collected.reverse()
        return collected

    def stream_answer(self, text: str):
        """Inject the answer and resume, yielding one event per executed node, then the
        terminal teach/question/state/done events. Used by the SSE endpoint."""
        self.app.update_state(self.config, {"user_answer": text, "pending_answers": [],
                                            "user_intent": None})
        for update in self.app.stream(None, self.config, stream_mode="updates"):
            for node, delta in update.items():
                if node.startswith("__"):   # skip LangGraph control keys (e.g. __interrupt__)
                    continue
                yield self._step_event(node, delta or {})
        for ev in self._terminal_events():
            yield ev

    def stream_lost(self):
        """Learner said they're lost: set user_intent='lost', resume through handle_lost."""
        self.app.update_state(self.config, {"user_intent": "lost", "user_answer": None,
                                            "pending_answers": []})
        for update in self.app.stream(None, self.config, stream_mode="updates"):
            for node, delta in update.items():
                if node.startswith("__"):
                    continue
                yield self._step_event(node, delta or {})
        for ev in self._terminal_events():
            yield ev

    def current(self) -> dict:
        snap = self.app.get_state(self.config)
        vals = snap.values
        route = vals.get("route") or []
        done = bool(route) and all(
            st.get("status") in self._TERMINAL_ROUTE_STATUSES for st in route
        )

        teach_messages = self._recent_teach_messages(vals.get("history", []))
        teach_msg = teach_messages[-1] if teach_messages else None

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
            "teach_messages": teach_messages,
            "question": quiz.get("question"),
            "bloom": quiz.get("bloom_level"),
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
                for st in route
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
            "graph": to_svg(concept_graph(self.conn, self.sid)),
        }


class AgentSession:
    """Conversation layer over the teaching graph. Holds the transcript and a lazily-created
    TutorSession; handle(message) dispatches each turn and yields UI events. The teaching
    graph is never modified — set_goal/answer go through TutorSession unchanged."""

    _BUDGET = 120000

    def __init__(self, domain_conn, checkpoint_conn, session_id: str, fixture_data: dict | None = None,
                 *, open_world_goal: str | None = None, live: bool = False, out_dir: str = "artifacts"):
        self.conn = domain_conn
        self.ckpt = checkpoint_conn
        self.sid = session_id
        self.out_dir = out_dir
        # Open-world (live) mode: no fixture — build this learner's own graph from real sources.
        self.open_world = bool(open_world_goal and live)
        self.goal = (open_world_goal or "").strip()
        self.built = False
        self.tutor: TutorSession | None = None
        if fixture_data:
            self.data = fixture_data
            self.concepts = fixture_data["concepts"]
            self.off = fixture_data["induction"]["off_skeleton"]
            self.topic = fixture_data.get("topic", "agents")
        else:
            self.data = None
            self.concepts = []
            self.off = None
            self.topic = self.goal or "agents"

    def _cur(self) -> dict:
        return self.tutor.current() if self.tutor else {}

    def _quiz_pending(self) -> bool:
        cur = self._cur()
        return bool(self.tutor and not cur.get("done") and cur.get("question"))

    def current(self) -> dict:
        """Snapshot for the initial page render (empty 'conversing' state before teaching)."""
        if self.open_world and not self.built:
            # "Building your course" placeholder — the page auto-streams the cold start on load.
            return {"done": False, "building": True, "goal": self.goal, "concept_name": None,
                    "teach": None, "teach_messages": [], "question": None, "route": [],
                    "route_version": 1, "learner": [], "cited": [], "evidence": [],
                    "decision": None, "rationale": None, "induced": [], "intent": None,
                    "mastery": None, "confidence": None,
                    "graph": to_svg(concept_graph(self.conn, None))}
        if self.tutor:
            return self.tutor.current()
        return {"done": False, "concept_name": None, "teach": None, "teach_messages": [], "question": None,
                "route": [], "route_version": 1, "learner": [], "cited": [], "evidence": [],
                "decision": None, "rationale": None, "induced": [], "intent": None,
                "mastery": None, "confidence": None,
                # Base concept map (no session state yet) — orients the learner before teaching.
                "graph": to_svg(concept_graph(self.conn, None))}

    def current_events(self):
        if self.open_world and not self.built:
            return self._build_open_world()
        if self.tutor:
            return self.tutor._terminal_events()
        return [{"type": "reply",
                 "text": "Hi! Tell me what you'd like to learn from the agent papers."},
                {"type": "done", "done": False}]

    def _build_open_world(self):
        """Cold start (live): discover real sources → digest into a per-session concept graph →
        teach from it. Yields coarse 'build' stage events, then the teach terminal events."""
        yield {"type": "build", "stage": "discover", "label": f"Finding real sources for: {self.goal}",
               "skill": "find-sources", "method": "BM25 + embedding rerank + relevance gate",
               "paper": "Robertson; Cohan 2020"}
        try:
            res = find_sources.find(DiscoverInput(self.goal, k=6), conn=self.conn,
                                    session_id=self.sid, budget=self._BUDGET)
        except Exception as e:
            yield {"type": "reply", "kind": "boundary", "text": f"Source search failed: {e}"}
            yield {"type": "done", "done": False}
            return
        withft = [s for s in res.sources if s.chunks and sum(len(x) for x in s.chunks) > 200]
        if not withft:
            yield {"type": "reply", "kind": "boundary",
                   "text": f"I couldn't find an open, full-text source for “{self.goal}”. "
                           "Try rephrasing, or a more specific topic."}
            yield {"type": "done", "done": False}
            return
        top = withft[0]
        yield {"type": "build", "stage": "discover_done", "label": f"Source: {top.title[:80]}"}
        yield {"type": "build", "stage": "digest", "label": "Reading it and building your concept map…",
               "skill": "digest-corpus", "method": "concept extraction + RefD prereqs + gpt-4o verify",
               "paper": "Liang 2015"}
        di = DigestInput(self.goal,
                         [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                         target_slugs=[])
        pipeline.digest(di, conn=self.conn,
                        candidate={"concepts": [], "keypoints": [], "prereq_edges": [],
                                   "similarity_edges": [], "quiz_seeds": [], "judge_labels": {}},
                        session_id=self.sid, budget=self._BUDGET)
        tids = [r[0] for r in self.conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:4]
        if not tids:
            yield {"type": "reply", "kind": "boundary",
                   "text": "I read the source but couldn't extract teachable concepts. Try another topic."}
            yield {"type": "done", "done": False}
            return
        # Repopulate concepts from the freshly-built graph so dispatch works during teaching.
        self.concepts = [{"id": r[0], "slug": r[1], "name": r[2]} for r in
                         self.conn.execute("SELECT id, slug, name FROM concepts ORDER BY id").fetchall()]
        yield {"type": "build", "stage": "map", "label": f"Concept map ready — {len(tids)} concepts",
               "graph": to_svg(concept_graph(self.conn, self.sid))}
        self.tutor = TutorSession(self.conn, self.ckpt, self.sid, out_dir=self.out_dir)
        self.tutor.start(self.goal, target_concept_ids=tids, goal_text=self.goal, mastery_threshold=0.75)
        self.built = True
        for ev in self.tutor._terminal_events():
            yield ev

    def _start_teaching(self, slug: str):
        slug_to_id = {c["slug"]: c["id"] for c in self.concepts}
        self.tutor = TutorSession(self.conn, self.ckpt, self.sid, out_dir=self.out_dir)
        if self.off and slug == self.off["slug"]:
            self.tutor.start(self.topic, target_concept_ids=[],
                             pending_induction=self.data["induction"], mastery_threshold=0.75)
        else:
            self.tutor.start(self.topic, target_concept_ids=[slug_to_id[slug]],
                             mastery_threshold=0.75)
        for ev in self.tutor._terminal_events():
            yield ev

    def _grounded_aside(self, message: str, slug: str) -> str:
        """A short answer to the learner's specific side question, grounded ONLY in that
        concept's top chunk."""
        slug_to_id = {c["slug"]: c["id"] for c in self.concepts}
        cid = slug_to_id.get(slug)
        if cid is None:
            return "That's outside what these papers cover — let's stay with the question."
        ev = retrieve_node({"current_concept_id": cid}, self.conn).get("current_evidence") or []
        if not ev:
            return "I don't have evidence on that here — let's stay with the question."
        chunk = ev[0]
        from litnav.llm import client as llm_client
        det = chunk["text"][:200].rstrip() + "…"
        prompt = (f"The learner asked: {message!r}\n"
                  "Answer THAT question in ONE short sentence, grounded ONLY in the evidence "
                  f"below; do not add facts beyond it.\nEvidence:\n{chunk['text']}")
        return llm_client.complete_text(prompt, fallback=det, max_tokens=80)

    def _boundary_reply(self, message: str) -> str:
        """Honest bridge when the learner wants something OUTSIDE the paper pack (e.g. linear
        algebra under an agent paper). Names the topic, declines to fake-teach it, and points
        back to what is teachable — never grounded teaching. Deterministic fallback offline."""
        names = ", ".join(c["name"] for c in self.concepts)
        fallback = ("That's outside my literature pack — I'm built only from these agent papers, "
                    f"so I won't pretend to teach it. I can teach: {names}.")
        from litnav.llm import client as llm_client
        prompt = (
            "You are a tutor built ONLY from a fixed pack of LLM-agent papers. The learner asked "
            "for something OUTSIDE that pack. Do NOT teach it. In 2-3 warm sentences: name the "
            "topic they asked about, say plainly it is outside your literature pack so you will "
            "not fake-teach it, and point them back to what you CAN teach. Do not add domain "
            "facts beyond naming the topic.\n"
            f"Teachable concepts: {[c['name'] for c in self.concepts]}\n"
            f"Learner message: {message!r}"
        )
        return llm_client.complete_text(prompt, fallback=fallback, max_tokens=120)

    def handle(self, message: str):
        if self.open_world and not self.built:
            # First turn in live open-world mode: run the cold-start build (goal already known).
            yield from self._build_open_world()
            return
        cur = self._cur()
        pending = self._quiz_pending()
        question = cur.get("question") if pending else None
        d = dispatch(message, concepts=self.concepts, off=self.off,
                     quiz_pending=pending, question=question)
        yield {"type": "dispatch", "action": d["action"],
               "label": f"understood as: {d['action']}"}

        if d["action"] == "answer":
            yield from self.tutor.stream_answer(message)
        elif d["action"] == "lost":
            yield from self.tutor.stream_lost()
        elif d["action"] == "set_goal":
            yield from self._start_teaching(d["slug"])
        elif d["action"] == "aside":
            # Don't trust the LLM's aside concept — resolve it deterministically from the
            # message, so an off-corpus side topic (e.g. "chain-of-thought") declines
            # gracefully instead of grounding on a loosely-related concept.
            from litnav.goal import resolve_goal
            r = resolve_goal(message, self.concepts, self.off)
            aside_slug = r["slug"] if r["kind"] == "concept" else None
            if aside_slug is None:
                # Off-corpus side topic (e.g. "first teach me linear algebra"): honest boundary
                # bridge instead of a curt "stay with the question".
                yield {"type": "reply", "text": self._boundary_reply(message), "kind": "boundary"}
            else:
                yield {"type": "reply", "text": self._grounded_aside(message, aside_slug)}
            if question:
                yield {"type": "question", "text": question, "bloom_level": cur.get("bloom")}
            yield {"type": "done", "done": False}
        elif d["action"] == "out_of_scope" and _looks_learn_request(message):
            # The learner wants to learn something we don't have — decline honestly and name it,
            # rather than a flat "I can teach: …" list. (Greetings/chit-chat fall through to chat.)
            yield {"type": "reply", "text": self._boundary_reply(message), "kind": "boundary"}
            if question:
                yield {"type": "question", "text": question, "bloom_level": cur.get("bloom")}
            yield {"type": "done", "done": bool(cur.get("done"))}
        else:  # chat, or out_of_scope that isn't a learn request (e.g. a greeting)
            yield {"type": "reply", "text": d["reply"] or "What would you like to learn?"}
            if question:
                yield {"type": "question", "text": question, "bloom_level": cur.get("bloom")}
            yield {"type": "done", "done": bool(cur.get("done"))}
