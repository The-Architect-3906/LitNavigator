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
