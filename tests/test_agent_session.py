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
