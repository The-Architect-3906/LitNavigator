import sqlite3, uuid
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession
from litnav.ui.trace import build_trace


def test_lecture_turn_appears_in_trace_timeline():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn); seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    ts = TutorSession(conn, ckpt, str(uuid.uuid4()))
    ts.start("agents", target_concept_ids=[2], mastery_threshold=0.75)  # tool_use: quizless -> lecture
    t = build_trace(conn, ts.sid)
    lectures = [e for e in t["timeline"] if e["turn_type"] == "lecture"]
    assert lectures, "the quizless lecture turn must appear in the judge-facing timeline"
    ev = lectures[0]
    assert ev["name"] == "Tool use"
    assert ev["decision"] == "lecture"
    assert "no mastery" in ev["rationale"]
    assert ev["mastery_after"] is None and ev["answer"] is None
