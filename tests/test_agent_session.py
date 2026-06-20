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


def test_out_of_corpus_learn_request_gets_honest_boundary(monkeypatch):
    """The linear-algebra case: a learn request for something OUTSIDE the paper pack must get
    a graceful honest decline (kind='boundary'), not a flat list and not fake teaching."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    evs = list(a.handle("teach me linear algebra first"))
    assert "teach" not in _types(evs) and a.tutor is None      # never fake-teaches it
    reply = next(e for e in evs if e["type"] == "reply")
    assert reply.get("kind") == "boundary"
    assert "outside" in reply["text"].lower() or "literature" in reply["text"].lower()


def test_greeting_is_not_treated_as_boundary(monkeypatch):
    """A greeting is out_of_scope too, but it is NOT a learn request — keep the friendly reply,
    don't slap an 'outside my pack' decline on a hello."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    reply = next(e for e in a.handle("hello there") if e["type"] == "reply")
    assert reply.get("kind") != "boundary"


def test_off_corpus_aside_during_quiz_is_boundary(monkeypatch):
    """Mid-lesson, asking to learn an out-of-corpus prereq must give the honest boundary reply
    and re-pose the pending question, not grade it and not dismiss it."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))               # now a quiz is pending
    evs = list(a.handle("I want to learn linear algebra first"))
    reply = next(e for e in evs if e["type"] == "reply")
    assert reply.get("kind") == "boundary"
    assert "question" in _types(evs)                           # the quiz is re-posed
    assert "state" not in _types(evs)                          # it was NOT graded


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


def test_reteach_request_during_quiz_is_not_graded_as_answer(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))   # quiz now pending

    before = a.conn.execute("SELECT count(*) FROM quiz_attempts").fetchone()[0]
    evs = list(a.handle("I want to understand ReAct"))
    after = a.conn.execute("SELECT count(*) FROM quiz_attempts").fetchone()[0]

    t = _types(evs)
    assert "reply" in t
    assert "question" in t
    assert "state" not in t
    assert after == before


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


def test_wrong_answer_triggers_reteach_kp(monkeypatch):
    """A wrong answer in the TEACH/ASSESS flow triggers per-keypoint reteach (not replan).

    multi_agent now has a keypoint (kp_multi_1) so it uses the new TEACH/ASSESS path.
    Wrong answer → reteach_kp with a fresh strategy; same bloom level re-quizzed.
    """
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand multi agent systems"))
    cur = a.tutor.current()
    assert cur.get("question"), "multi_agent must pose a quiz after teaching all keypoints"
    # Give a clearly wrong answer
    evs = list(a.handle("it just stores data"))
    t = _types(evs)
    step_labels = [e.get("label", "") for e in evs if e["type"] == "step"]
    # New behavior: wrong answer → reteach_kp (not replan)
    assert any("re-teach" in lbl.lower() or "reteach" in lbl.lower() for lbl in step_labels), \
        f"expected a reteach_kp step, got: {step_labels}"
    # A new quiz must be posed after reteach
    assert "question" in t, "quiz must be re-posed after reteach"
