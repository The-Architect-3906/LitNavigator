"""A1/B1 regression: a correct learner on a DIGESTED concept must reach mastery (done),
not concede.

Root cause (pre-fix): `litnav/digest/pipeline.py::_propose_quiz_seeds` wrote ONE recall-level
seed per concept. With a single quiz the always-correct learner gets exactly one correct
observation, and `kp_confidence(1)=0.30 < KP_CONF_THRESHOLD (0.50)`, so the concept-level
advance gate never clears and the concept ends in `concede` instead of `done` — the stated
learning goal is unreachable.

This test builds a digested concept the way the digest path does (it runs the real `digest()`
pipeline against a candidate that has ONE recall seed, exactly like `_propose_quiz_seeds`'s
historical output), then drives teach -> assess -> grade -> advance with an always-correct
learner and asserts the concept reaches `done`.

Runs offline (provider=none -> deterministic fallback grader): the fallback marks an answer
correct iff it contains the answer_key, so we always answer with the key.
"""
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.nodes.teach_kp import init_concept_progress, teach_kp_node, route_after_teach_kp
from litnav.nodes.assess_next import assess_next_node
from litnav.nodes.grade_kp import grade_kp_node, assess_decider
from litnav.nodes.route_decider import advance_kp_node

ANSWER_KEY = "reasoning traces and actions"

# Candidate shaped like the historical digest output: ONE recall seed for the concept.
CANDIDATE = {
    "concepts": [
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
    ],
    "keypoints": [
        {"kp_id": "kp_ra_1", "concept_slug": "reason_act", "name": "Interleave thought and action",
         "objective": "explain ReAct", "evidence_chunk_id": "c0", "bloom_level": "recall"},
    ],
    "prereq_edges": [],
    "similarity_edges": [],
    "quiz_seeds": [
        {"concept_slug": "reason_act", "question": "What does ReAct interleave?",
         "answer_key": ANSWER_KEY, "keypoint_id": "kp_ra_1", "bloom_level": "recall"},
    ],
    "judge_labels": {},
}


def _digest_concept(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "topic")
    di = DigestInput(
        "llm-agents",
        [SourceDoc("arxiv", "2210.03629", "ReAct",
                   None, ["ReAct interleaves reasoning traces and actions and observations."])],
        target_slugs=[],
    )
    pipeline.digest(di, conn=c, candidate=CANDIDATE, session_id="s")
    cid = c.execute("SELECT id FROM concepts WHERE slug='reason_act'").fetchone()[0]
    repo.upsert_learner_state(c, "s", cid, mastery=0.4, confidence=0.0, n_observations=0)
    return c, cid


def _base_state(cp, cid):
    return {
        "session_id": "s", "route_version": 1, "current_cited_chunks": [],
        "route": [{"concept_id": cid, "step_id": "r1", "status": "pending"}],
        "concept_dag": {cid: []}, "learner_state": {cid: {"mastery": 0.4}},
        "mastery_threshold": 0.75, "bloom_ceiling": None,
        "concept_progress": cp, "history": [],
        "pending_answers": [], "user_answer": None, "current_quiz_item": None,
    }


def test_correct_learner_reaches_mastery_on_digested_concept(monkeypatch):
    c, cid = _digest_concept(monkeypatch)
    cp = init_concept_progress(cid, c)
    state = _base_state(cp, cid)

    # TEACH all keypoints first
    while route_after_teach_kp(state) == "teach_kp":
        out = teach_kp_node(state, c)
        state.update(out)
        state["history"] = state["history"] + out.get("history", [])

    # ASSESS -> GRADE -> decide loop with an always-correct learner
    decision = None
    for _ in range(20):  # generous bound; should terminate well before this
        out = assess_next_node(state, c)
        state.update(out)
        state["history"] = state["history"] + out.get("history", [])
        if state.get("current_quiz_item") is None:
            out = advance_kp_node(state, c)   # no quiz left -> route decider (concede path)
            state.update(out)
            decision = out["decision"]
            break

        state["pending_answers"] = [f"ReAct interleaves {ANSWER_KEY} and observations"]
        out = grade_kp_node(state, c)
        state.update(out)
        state["history"] = state["history"] + out.get("history", [])

        route = assess_decider(state)
        if route == "advance_kp":
            out = advance_kp_node(state, c)
            state.update(out)
            decision = out["decision"]
            break
        # else assess_next / reteach_kp -> loop again
    else:
        raise AssertionError("teach/assess loop did not terminate")

    assert decision == "advance", (
        f"correct learner should reach mastery (advance), got {decision!r}; "
        f"route step statuses={[s['status'] for s in state['route']]}"
    )
    assert any(s["status"] == "done" for s in state["route"]), "concept never marked done"
