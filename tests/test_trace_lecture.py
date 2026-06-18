import sqlite3, uuid
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession
from litnav.ui.trace import build_trace


def test_lecture_turn_appears_in_trace_timeline():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    # agents_expanded.json: tool_use (id 2) is quizless AND has cited evidence — the case where a
    # lecture both routes through lecture_node and has an evidence chain to surface.
    init_db(conn); seed_demo_data(conn, "data/seed/agents_expanded.json")
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
    # The rationale claims it was "taught from cited evidence" — that evidence chain must be
    # visible to a judge, not dropped to "cites —".
    assert ev["cited_chunks"], "lecture turn must surface the chunks it was taught from"
    cited_in_evidence = {e["chunk_id"] for e in t["evidence"]}
    assert set(ev["cited_chunks"]) <= cited_in_evidence, \
        "every chunk a lecture cites must appear in the trace evidence list"
