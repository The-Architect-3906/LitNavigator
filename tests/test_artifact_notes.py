import sqlite3
from litnav.storage.schema import init_db
from litnav.artifact.renderers import notes
from litnav.llm import router

CONCEPTS = [{"slug": "react", "name": "ReAct"}, {"slug": "tool_use", "name": "Tool Use"}]
EV = {"react": ["ReAct interleaves reasoning traces and actions."],
      "tool_use": ["Tools let the agent act on the world."]}

def test_notes_offline_cornell_template(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = notes.render(CONCEPTS, EV, citations=["c0", "c1"], conn=c, session_id="s")
    # Cornell structure: self-test questions + key takeaway
    assert "Self-test questions" in out and "Key takeaway" in out
    assert "ReAct" in out and "Tool Use" in out
    # Citations section with chunk IDs (no paper row in memory DB → raw id shown)
    assert "Sources" in out and "c0" in out
    assert any(w in out.lower() for w in ("recall", "retrieval", "test yourself", "without looking"))
    # NOT verbatim: full evidence sentence should not be dumped wholesale
    assert out.count("ReAct interleaves reasoning traces and actions.") <= 1

def test_notes_live_uses_llm(monkeypatch):
    captured = {}
    def fake(prompt, *, tier, stage, fallback, **k):
        captured["called"] = True
        return {"notes": [{"concept": "ReAct", "cues": ["what is ReAct?"],
                           "explanation": "ReAct combines reasoning and acting.",
                           "summary": "reasoning+acting"}]}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = notes.render(CONCEPTS, EV, citations=["c0"], conn=c, session_id="s")
    assert captured.get("called") and "reasoning+acting" in out
    assert "ReAct combines reasoning and acting." in out
