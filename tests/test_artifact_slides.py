import sqlite3
from litnav.storage.schema import init_db
from litnav.artifact.renderers import slides
from litnav.llm import router

CONCEPTS = [{"slug": "react", "name": "ReAct"}, {"slug": "tool_use", "name": "Tool Use"}]
EV = {"react": ["ReAct interleaves reasoning and acting."], "tool_use": ["Tools act on the world."]}

def test_slides_offline_is_valid_marp(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = slides.render(CONCEPTS, EV, citations=["c0", "c1"], conn=c, session_id="s")
    assert out.startswith("---")                      # Marp front-matter
    assert "marp: true" in out
    assert out.count("\n---\n") >= 2                  # slide separators (title + >=1 content + citations)
    assert "ReAct" in out and "Tool Use" in out
    assert "Citations" in out and "c0" in out
    assert any(w in out.lower() for w in ("recall", "retrieval", "test yourself"))  # retrieval prompt

def test_slides_uses_llm_outline_then_deterministic_emit(monkeypatch):
    def fake(prompt, *, tier, stage, fallback, **k):
        return {"slides": [{"title": "ReAct", "bullets": ["interleaves reasoning", "and acting"]}]}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = slides.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert "interleaves reasoning" in out and "marp: true" in out
