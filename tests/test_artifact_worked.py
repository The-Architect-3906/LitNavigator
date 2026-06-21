import sqlite3
from litnav.storage.schema import init_db
from litnav.artifact.renderers import worked_example
from litnav.llm import router

CONCEPTS = [{"slug": "gradient_descent", "name": "Gradient Descent"}]
EV = {"gradient_descent": ["Update params opposite the gradient, scaled by a learning rate."]}

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

def test_worked_uses_llm_then_assembles(monkeypatch):
    def fake(prompt, *, tier, stage, fallback, **k):
        return {"steps": ["Compute the gradient", "Step opposite it"],
                "practice": {"question": "What sign is the step?", "answer": "Negative gradient direction"}}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = worked_example.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert "Compute the gradient" in out and "What sign is the step?" in out
