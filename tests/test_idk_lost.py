# tests/test_idk_lost.py
"""A5/B7: "I don't know" family must route to 'lost' (no-penalty re-explain), not 'answer'."""
import json
import pytest
from litnav.conversation import dispatch

_DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))
CONCEPTS = _DATA["concepts"]
OFF = _DATA["induction"]["off_skeleton"]


def _ctx(quiz_pending=True, question="What does ReAct stand for?"):
    return dict(concepts=CONCEPTS, off=OFF, quiz_pending=quiz_pending, question=question)


@pytest.mark.parametrize("msg", [
    "I don't know",
    "I dont know",
    "idk",
    "don't know",
])
def test_idk_routes_to_lost_during_quiz(monkeypatch, msg):
    """'I don't know' variants must never be graded — they route to the lost/re-explain path."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch(msg, **_ctx())
    assert d["action"] == "lost", f"{msg!r} was classified as {d['action']!r}, expected 'lost'"


def test_im_lost_still_routes_to_lost(monkeypatch):
    """Regression: existing 'I'm lost' cue must continue to work."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("I'm lost", **_ctx())
    assert d["action"] == "lost"


def test_genuine_answer_still_routes_to_answer(monkeypatch):
    """A real answer attempt must not be reclassified as lost."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("the agent uses actions and observations in a loop", **_ctx())
    assert d["action"] == "answer"


def test_idk_llm_override_stays_lost(monkeypatch):
    """Even if a live LLM labels 'idk' as 'answer', the lost guard must override it."""
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "answer", "slug": None, "reply": ""})
    d = dispatch("idk", **_ctx())
    assert d["action"] == "lost"
