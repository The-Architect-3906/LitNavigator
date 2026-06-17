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
