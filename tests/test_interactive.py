import sqlite3
import uuid

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession

M2 = "data/seed/agents_m2.json"
REACT = 1


def _session():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, M2)
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    return TutorSession(conn, ckpt, str(uuid.uuid4()))


def test_pauses_with_a_question_then_advances_on_correct_answer():
    ts = _session()
    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    assert not s["done"], "tutor pauses for the learner"
    assert s["question"], "a quiz question is presented"
    assert s["concept_name"].startswith("ReAct")
    assert s["teach"], "a teaching turn was produced"

    s = ts.answer("the agent takes actions and observations")
    assert s["done"], "only ReAct targeted -> route finishes after a correct answer"
    assert s["mastery"] >= 0.75


def test_wrong_answer_triggers_reteach_then_pass():
    ts = _session()
    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)

    s = ts.answer("it is just chain of thought")          # wrong -> misconception -> reteach
    assert not s["done"], "reteach loops back with a new question"
    assert s["question"]
    assert s["last_detected_misconception"] == "react_is_just_cot"

    s = ts.answer("the agent takes actions and observations")  # correct after reteach
    assert s["done"]
    assert s["mastery"] >= 0.75


def test_keypoint_wrong_answer_reteaches_and_reasks():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    ts = TutorSession(conn, ckpt, str(uuid.uuid4()))

    ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    s = ts.answer("I don't know")

    assert not s["done"], "wrong answer should not end the session"
    assert s["question"], "after reteach the learner should receive another quiz prompt"
    assert s["teach_messages"], "reteach explanation should remain visible in the live state"
    assert "different approach" in s["teach_messages"][-1].lower()


def test_interactive_induction_then_teach():
    """Off-skeleton request: the live session induces the scaffold, then teaches it interactively."""
    import json
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m3.json")
    cand = json.loads(open("data/seed/agents_m3.json", encoding="utf-8").read())["induction"]
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    ts = TutorSession(conn, ckpt, str(uuid.uuid4()))

    s = ts.start("agents", target_concept_ids=[], pending_induction=cand, mastery_threshold=0.75)
    assert not s["done"]
    assert s["concept_name"] == "Multi-agent debate"      # induced concept is being taught
    assert s["question"]
    s = ts.answer("they critique and refine each other's answers")
    assert s["done"] and s["mastery"] >= 0.75


def test_current_exposes_live_glass_box_before_answering():
    ts = _session()
    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    assert s["route"], "route is visible during teaching (from the checkpoint)"
    assert any(step["concept_id"] == REACT for step in s["route"])
    assert s["evidence"], "the chunk(s) being taught now are visible before any answer"
    assert s["route_version"] == 1


def _session_full():
    """A session over the full 7-concept agent fixture (needed for intent re-scoping)."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    return TutorSession(conn, ckpt, str(uuid.uuid4()))


def test_intent_modes_rescope_the_same_corpus_to_different_routes():
    """Same corpus, different purpose -> different routes (the novelty contrast)."""
    researcher = [s["concept_id"] for s in _session_full().start("agents", intent="researcher")["route"]]
    journalist = [s["concept_id"] for s in _session_full().start("agents", intent="journalist")["route"]]
    assert researcher and journalist
    assert researcher != journalist, "intent must re-scope the route"
    assert len(researcher) > len(journalist), "researcher route is the deeper one"


def test_current_cited_is_only_the_cited_chunk():
    ts = _session()
    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    assert s["cited"], "the cited chunk(s) are exposed for the glass box"
    cited_ids = {c["chunk_id"] for c in s["cited"]}
    ev_ids = {e["chunk_id"] for e in s["evidence"]}
    assert cited_ids <= ev_ids, "cited is a subset of retrieved evidence"
    assert len(s["cited"]) <= len(s["evidence"])
    assert all(cid.startswith("c_react") for cid in cited_ids), "cited the curated react chunk"


def test_keypoint_concept_shows_teach_phase_before_first_quiz():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    ts = TutorSession(conn, ckpt, str(uuid.uuid4()))

    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)

    assert not s["done"], "keypoint concept should pause for the first quiz, not complete early"
    assert s["question"], "the first adaptive quiz should be ready after the teach phase"
    assert len(s["teach_messages"]) >= 2, "all keypoint teach turns should be visible before quizzing"
    assert any("reasoning and acting" in msg.lower() for msg in s["teach_messages"])
    assert any("plain chain-of-thought" in msg.lower() or "chain-of-thought" in msg.lower()
               for msg in s["teach_messages"])


def test_stream_answer_emits_steps_and_terminal_events():
    ts = _session()
    ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    events = list(ts.stream_answer("it is just chain of thought"))  # wrong -> misconception -> reteach
    types = [e["type"] for e in events]
    nodes = [e["node"] for e in events if e["type"] == "step"]
    assert "grade" in nodes
    assert any(n in ("reteach", "teach") for n in nodes), "reteach/teach step streamed"
    assert "teach" in types and "question" in types and "state" in types
    assert types[-1] == "done"
    assert all(not n.startswith("__") for n in nodes), "LangGraph control keys are filtered out"
    grade_ev = next(e for e in events if e.get("node") == "grade")
    assert "react_is_just_cot" in grade_ev["detail"], "grade step carries the detected misconception"


def test_quizless_concept_lectures_and_advances_without_stall():
    """A concept with no quiz must not stall the session at an empty quiz interrupt."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn); seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    ts = TutorSession(conn, ckpt, str(uuid.uuid4()))
    s = ts.start("agents", target_concept_ids=[2], mastery_threshold=0.75)  # tool_use: no quiz
    assert s["done"] is True, "quizless concept should lecture then advance, not stall"
    assert s["question"] is None
    # honesty: the quizless concept is recorded as a lecture, NOT 'advanced' as mastered,
    # and no decision falsely claims mastery >= threshold.
    rows = conn.execute("SELECT decision, rationale FROM decisions WHERE session_id=?",
                        (ts.sid,)).fetchall()
    decisions = {r[0] for r in rows}
    assert "lecture" in decisions and "advance" not in decisions
    assert all(">= threshold" not in (r[1] or "") for r in rows), "no false mastery claim"
    assert s["mastery"] is None, "an unassessed (lecture-only) route makes no mastery claim"
