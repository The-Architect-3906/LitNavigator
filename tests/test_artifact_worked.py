import sqlite3
from litnav.storage.schema import init_db
from litnav.artifact.renderers import worked_example
from litnav.llm import router

CONCEPTS = [{"slug": "gradient_descent", "name": "Gradient Descent"}]
EV = {"gradient_descent": ["Update params opposite the gradient, scaled by a learning rate."]}

import os as _os_live
import pytest as _pytest_live
_LIVE_ONLY = _pytest_live.mark.skipif(
    _os_live.getenv("LITNAV_LLM_PROVIDER", "none").lower() == "none",
    reason="live LLM path — activates only when a provider is configured; "
           "skipped in the $0 offline suite",
)


def test_worked_offline_has_steps_and_practice(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = worked_example.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert "Gradient Descent" in out
    assert "Worked Example" in out                       # worked-example heading
    assert any(w in out for w in ("Step 1", "1.", "Step"))  # step-by-step
    assert "Practice" in out                             # a practice item
    assert "Answer" in out or "answer" in out            # with an answer
    assert "Citations" in out and "c0" in out
    assert any(w in out.lower() for w in ("recall", "retrieval", "test yourself"))  # retrieval prompt

@_LIVE_ONLY
def test_worked_uses_llm_then_assembles(monkeypatch):
    def fake(prompt, *, tier, stage, fallback, **k):
        return {"steps": ["Compute the gradient", "Step opposite it"],
                "practice": {"question": "What sign is the step?", "answer": "Negative gradient direction"}}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = worked_example.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert "Compute the gradient" in out and "What sign is the step?" in out

@_LIVE_ONLY
def test_worked_strips_llm_enumerator_no_double_numbering(monkeypatch):
    # LLM sometimes pre-numbers steps ("1. ...", "Step 1 — ..."); the emitter re-numbers,
    # so the leading enumerator must be stripped to avoid "1. 1. ..." (seen in live output).
    def fake(prompt, *, tier, stage, fallback, **k):
        return {"steps": ["1. The agent fails a trajectory", "Step 2 — it writes a critique"],
                "practice": {"question": "q?", "answer": "a"}}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = worked_example.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert "1. 1." not in out and "1. Step 2" not in out
    assert "1. The agent fails a trajectory" in out
    assert "2. it writes a critique" in out
