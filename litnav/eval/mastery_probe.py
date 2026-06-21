"""Multi-turn mastery probe — the learning-gain signal for the eval loop.

Drives a scripted learner through each fixture concept's REAL keypoint cycle
(teach_kp -> assess_next -> grade_kp -> reteach_kp / advance_kp, using the actual nodes and the
`assess_decider` router) and measures whether the tutor brings the learner to mastery, how fast, and
whether it recovers from a wrong answer. Runs offline (provider=none -> deterministic fallback
grader) so it is $0, stable, and safe to run every loop iteration.
"""
from __future__ import annotations

import sqlite3

from litnav.state import KP_CONF_THRESHOLD, KP_MASTERY_THRESHOLD, kp_confidence
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.nodes.teach_kp import init_concept_progress, teach_kp_node, route_after_teach_kp
from litnav.nodes.assess_next import assess_next_node
from litnav.nodes.grade_kp import grade_kp_node, assess_decider
from litnav.nodes.reteach_kp import reteach_kp_node
from litnav.nodes.route_decider import advance_kp_node

_BLOOMS = ["recall", "comprehension", "application"]

# Small fixture: 3 concepts, each one keypoint with a quiz per bloom level so the ladder can climb.
_FIXTURE = [
    {"cid": 1, "slug": "react", "name": "ReAct", "kp": "kp_react",
     "kp_name": "Reason-act loop", "answer": "reasoning and acting"},
    {"cid": 2, "slug": "rag", "name": "RAG", "kp": "kp_rag",
     "kp_name": "Grounded retrieval", "answer": "retrieve then generate"},
    {"cid": 3, "slug": "bkt", "name": "BKT", "kp": "kp_bkt",
     "kp_name": "Knowledge tracing", "answer": "estimate mastery from observations"},
]


def _build_fixture(conn: sqlite3.Connection) -> None:
    repo.create_session(conn, "probe", "probe")
    for f in _FIXTURE:
        repo.create_concept(conn, f["cid"], f["slug"], f["name"])
        repo.create_keypoint(conn, f["kp"], f["cid"], f["kp_name"],
                             f"Explain {f['kp_name']}.", evidence_chunk_id=None,
                             sort_order=0, bloom_level="recall")
        repo.upsert_learner_state(conn, "probe", f["cid"], mastery=0.4, confidence=0.0, n_observations=0)
        # Two quiz items per bloom: a wrong answer + reteach needs a FRESH same-level question to
        # recover (assess_next marks each quiz used once), not a jump to the next bloom.
        for b in _BLOOMS:
            for v in (1, 2):
                repo.create_quiz_item(conn, f["cid"], f"[{b}#{v}] question for {f['name']}?",
                                      f["answer"], keypoint_id=f["kp"], bloom_level=b)


def _concept_mastery(cp: dict) -> float:
    ks = cp["keypoint_state"]
    return round(sum(s.get("mastery", 0.3) for s in ks.values()) / max(len(ks), 1), 3)


def _is_mastered(cp: dict) -> bool:
    ks = cp["keypoint_state"]
    m = sum(s.get("mastery", 0.3) for s in ks.values()) / max(len(ks), 1)
    c = kp_confidence(sum(s.get("correct_obs", 0) for s in ks.values()))
    return m >= KP_MASTERY_THRESHOLD and c >= KP_CONF_THRESHOLD


# --- scripted learners (answer_key, memo) -> answer string -------------------------------------
def lost_then_recover(answer_key: str, memo: dict) -> str:
    """Wrong on the first quiz of the run, correct after — exercises reteach recovery."""
    if not memo.get("done_first"):
        memo["done_first"] = True
        return "i am not sure"
    return answer_key


def always_correct(answer_key: str, memo: dict) -> str:
    return answer_key


def partial_then_full(answer_key: str, memo: dict) -> str:
    """Harder profile: give a PARTIAL answer (first half of the key idea) on the first attempt of
    each keypoint, then the full answer. Binary grading penalizes the partial (wrong→reteach);
    partial-credit grading should reward it — so this profile has headroom to show a grading change."""
    kp = memo.setdefault("_partial_seen", set())
    key = answer_key
    if key not in kp:
        kp.add(key)
        words = answer_key.split()
        return " ".join(words[: max(1, len(words) // 2)])  # partial: first half of the key idea
    return answer_key


def _run_concept(conn: sqlite3.Connection, f: dict, learner) -> dict:
    cid = f["cid"]
    state = {
        "session_id": "probe", "route_version": 1,
        "route": [{"step_id": 1, "concept_id": cid, "status": "pending"}],
        "concept_progress": init_concept_progress(cid, conn),
        "history": [], "pending_answers": [], "learner_state": {},
        "bloom_ceiling": None, "current_quiz_item": None, "user_intent": None,
    }
    m_start = _concept_mastery(state["concept_progress"])

    # TEACH every keypoint first (no quiz).
    while route_after_teach_kp(state) == "teach_kp":
        out = teach_kp_node(state, conn)
        state["concept_progress"] = out["concept_progress"]
        state["history"] += out.get("history", [])

    memo, reteached, mastered, turns = {}, False, False, 0
    for _ in range(15):  # turn cap
        out = assess_next_node(state, conn)
        state["concept_progress"] = out["concept_progress"]
        state["current_quiz_item"] = out.get("current_quiz_item")
        state["history"] += out.get("history", [])
        quiz = state["current_quiz_item"]
        if not quiz:                                   # no quiz → concept-level advance check
            advance_kp_node(state, conn)
            mastered = _is_mastered(state["concept_progress"])
            break
        state["pending_answers"] = [learner(quiz.get("answer_key", ""), memo)]
        out = grade_kp_node(state, conn)
        state["concept_progress"] = out["concept_progress"]
        state["learner_state"].update(out.get("learner_state", {}))
        state["history"] += out.get("history", [])
        turns += 1
        dec = assess_decider(state)
        if dec == "reteach_kp":
            reteached = True
            out = reteach_kp_node(state, conn)
            state["concept_progress"] = out["concept_progress"]
            state["history"] += out.get("history", [])
        elif dec == "advance_kp":
            advance_kp_node(state, conn)
            mastered = _is_mastered(state["concept_progress"])
            break
        # dec == "assess_next" → loop (bloom upgrades on the next pose)

    return {"mastered": mastered, "delta": round(_concept_mastery(state["concept_progress"]) - m_start, 3),
            "turns": turns, "reteached": reteached}


def run_probe(*, learner=lost_then_recover) -> dict:
    """Run the probe over the fixture concepts and aggregate the learning-gain signal."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _build_fixture(conn)
    results = [_run_concept(conn, f, learner) for f in _FIXTURE]
    n = len(results)
    recov = [r for r in results if r["reteached"]]
    return {
        "mastered_rate": round(sum(1 for r in results if r["mastered"]) / n, 3),
        "avg_mastery_delta": round(sum(r["delta"] for r in results) / n, 3),
        "avg_turns": round(sum(r["turns"] for r in results) / n, 2),
        "reteach_recovery": round(sum(1 for r in recov if r["mastered"]) / len(recov), 3) if recov else 1.0,
        "usd": 0.0,  # offline
    }


# Forgetting model for the delayed-retention metric: a concept is "retained" at the final re-quiz iff
# it was retrieved within _FORGET_WINDOW turns (being taught counts as a retrieval; a review_probe
# refreshes it). Deterministic + offline — proves the spaced-retrieval mechanism raises retention.
_FORGET_WINDOW = 2


def run_retention(*, probes_on: bool, k: int = 2) -> float:
    """Teach the fixture concepts in sequence (firing review probes between them when due, if on),
    then re-quiz each WITHOUT re-teaching. Returns the fraction retained for a forgetting learner."""
    from litnav.nodes.review_probe import pose_probe
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _build_fixture(conn)
    cids = [f["cid"] for f in _FIXTURE]
    route = [{"step_id": i + 1, "concept_id": c, "status": "pending"} for i, c in enumerate(cids)]
    concept_last_seen: dict = {}
    last_retrieval: dict = {}          # cid -> step it was last retrieved (taught or probed)
    step = 0
    for idx, cid in enumerate(cids):
        step += 1
        route[idx]["status"] = "done"
        concept_last_seen[cid] = step
        last_retrieval[cid] = step
        if probes_on:                 # fire a probe for the most-overdue earlier concept, if any
            st = {"session_id": "probe", "route": route, "learner_state": {},
                  "concept_last_seen": concept_last_seen, "step": step, "needs_review": [],
                  "now": "2026-06-22T00:00:00", "pending_answers": []}
            posed = pose_probe(st, conn, k=k)
            item = posed.get("current_quiz_item")
            if item:
                pcid = item["concept_id"]
                concept_last_seen.update(posed["concept_last_seen"])
                last_retrieval[pcid] = step          # the probe refreshes that concept
    final = step + 1
    retained = sum(1 for cid in cids if (final - last_retrieval[cid]) <= _FORGET_WINDOW)
    return round(retained / len(cids), 4)
