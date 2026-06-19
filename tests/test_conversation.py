# tests/test_conversation.py
import json
from litnav.conversation import dispatch

_DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))
CONCEPTS = _DATA["concepts"]
OFF = _DATA["induction"]["off_skeleton"]


def _ctx(quiz_pending=False, question=None):
    return dict(concepts=CONCEPTS, off=OFF, quiz_pending=quiz_pending, question=question)


def test_offline_quiz_pending_is_answer(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("the agent takes actions and observations", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "answer"


def test_offline_goal_is_set_goal(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("I want to understand ReAct", **_ctx())
    assert d["action"] == "set_goal" and d["slug"] == "react"


def test_offline_greeting_is_out_of_scope_with_guidance(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("你好", **_ctx())
    assert d["action"] == "out_of_scope"
    assert "ReAct" in d["reply"]   # names what it can teach


def test_llm_chat_action(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "chat", "slug": None, "reply": "Hi! What do you want to learn?"})
    d = dispatch("hello there", **_ctx())
    assert d["action"] == "chat" and "learn" in d["reply"]


def test_llm_aside_keeps_quiz(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "aside", "slug": "tool_use", "reply": ""})
    d = dispatch("wait, what is a tool?", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "aside" and d["slug"] == "tool_use"


def test_llm_aside_on_declarative_answer_is_coerced_to_answer(monkeypatch):
    """Harm-asymmetry guard: with a real provider the dispatcher can mislabel a terse
    declarative answer (e.g. 'actions and observations') as an aside — which would block the
    learner from ever being graded/advancing. A non-question message during a pending quiz
    must be treated as an answer attempt, not a side comment."""
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "aside", "slug": None, "reply": ""})
    d = dispatch("actions and observations", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "answer"


def test_llm_aside_on_real_question_stays_aside(monkeypatch):
    """The guard must NOT swallow genuine side-questions: a message that reads as a question
    (here, ends with '?') is still honored as an aside."""
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "aside", "slug": "tool_use", "reply": ""})
    d = dispatch("is it the same as a function call?", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "aside"


def test_hallucinated_slug_rejected(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "set_goal", "slug": "made_up", "reply": ""})
    d = dispatch("teach me made up thing", **_ctx())
    # invalid slug + set_goal with no quiz -> falls back to resolve_goal -> out_of_scope
    assert d["action"] == "out_of_scope"
