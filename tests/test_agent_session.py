# tests/test_agent_session.py
import json, sqlite3, uuid
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession

DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))


def _agent():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn); seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    return AgentSession(conn, ckpt, str(uuid.uuid4()), DATA)


def _types(events):
    return [e["type"] for e in events]


def test_greeting_replies_without_teaching(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    evs = list(a.handle("你好"))
    assert "reply" in _types(evs)              # a conversational reply
    assert "teach" not in _types(evs)          # nothing taught
    assert a.tutor is None                     # no teaching session created


def test_goal_starts_grounded_teaching(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    evs = list(a.handle("I want to understand ReAct"))
    assert "teach" in _types(evs) and "question" in _types(evs)
    assert a.tutor is not None


def test_answer_grades_after_goal(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))
    evs = list(a.handle("the agent takes actions and observations"))
    assert "state" in _types(evs) and _types(evs)[-1] == "done"


def test_aside_answers_then_reposes_quiz(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))   # quiz now pending
    from litnav.ui import interactive as I
    monkeypatch.setattr(I, "dispatch",
                        lambda *args, **kw: {"action": "aside", "slug": "react", "reply": ""})
    evs = list(a.handle("wait, what does ReAct stand for?"))
    t = _types(evs)
    assert "reply" in t                # a brief grounded aside answer
    assert "question" in t             # the quiz is re-posed
    # and the learner can still answer it
    evs2 = list(a.handle("the agent takes actions and observations"))
    assert _types(evs2)[-1] == "done"


def test_offline_aside_fallback_interrogative(monkeypatch):
    """Offline fallback routes interrogative messages as aside, not answer."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from litnav.conversation import _fallback
    concepts = DATA["concepts"]
    off = DATA["induction"]["off_skeleton"]
    # Yes/no question form ("is ...") — was previously mis-routed as answer
    r = _fallback("is multi agent system more secure", concepts, off, quiz_pending=True)
    assert r["action"] == "aside"
    # Open question form
    r2 = _fallback("what is tool use?", concepts, off, quiz_pending=True)
    assert r2["action"] == "aside"
    # Plain answer attempt stays as answer
    r3 = _fallback("it just retries the same prompt", concepts, off, quiz_pending=True)
    assert r3["action"] == "answer"


def test_wrong_answer_triggers_replan_in_live_ui(monkeypatch):
    """A wrong answer for a concept with an unmastered prereq replans and teaches the prereq.

    multi_agent has react as prereq AND has a quiz item, so it can trigger the
    diagnose→replan path. (tool_use has no quiz — it lectures and advances, so it
    can never expose a prereq gap via grading.)
    """
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    # multi_agent has react as prerequisite and has a quiz item
    list(a.handle("I want to understand multi agent systems"))
    cur = a.tutor.current()
    # Confirm we're actually at a quiz (not lectured-and-done)
    assert cur.get("question"), "multi_agent must have a quiz for this test to be meaningful"
    # Give a clearly wrong answer — grade marks it wrong, tutor_router sees unmastered prereq
    evs = list(a.handle("it just stores data"))
    t = _types(evs)
    # The graph should have run diagnose → replan → teach (react, the prereq)
    step_labels = [e.get("label", "") for e in evs if e["type"] == "step"]
    assert any("plan" in lbl.lower() for lbl in step_labels), \
        f"expected a replan step, got: {step_labels}"
    assert "teach" in t, "expected teaching of the prereq (react) after replan"
    # route_version should have incremented to 2
    state_ev = next((e for e in evs if e["type"] == "state"), None)
    assert state_ev is not None and state_ev["route_version"] == 2, \
        f"expected route_version=2, got: {state_ev}"
