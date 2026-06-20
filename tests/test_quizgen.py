import sqlite3
from litnav.storage.schema import init_db
from litnav.assess import quizgen
from litnav.llm import router


def test_make_distractors_offline_fallback(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    ds = quizgen.make_distractors("What does ReAct interleave?", "reasoning and acting",
                                  conn=c, session_id="s", n=3, fallback=["a", "b", "c", "d"])
    assert len(ds) == 3 and "reasoning and acting" not in ds   # never the answer; capped to n

def test_make_distractors_live_overgenerate_rank(monkeypatch):
    monkeypatch.setattr(router, "complete_json",
        lambda *a, **k: {"distractors": ["wrong1", "wrong2", "wrong3", "wrong4", "the answer"]})
    c = sqlite3.connect(":memory:"); init_db(c)
    ds = quizgen.make_distractors("q", "the answer", conn=c, session_id="s", n=3, fallback=[])
    assert len(ds) == 3 and "the answer" not in ds   # answer filtered out of distractors

def test_flaw_gate_rejects_bad_items():
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["a", "b", "c"]})[0] is True
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["x", "b", "c"]})[0] is False  # distractor == answer
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["a"]})[0] is False            # <2 distractors
    assert quizgen.flaw_gate({"question": "", "answer_key": "x", "distractors": ["a", "b"]})[0] is False        # empty stem

def test_estimate_difficulty_offline_mid(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    b = quizgen.estimate_difficulty({"question": "q", "answer_key": "x"}, conn=c, session_id="s")
    assert -3.0 <= b <= 3.0

def test_estimate_difficulty_weak_wrong_is_harder(monkeypatch):
    # weaker simulator gets it WRONG -> harder (higher irt_b) than when it gets it right
    def fake(prompt, *, tier, stage, fallback, **k):
        return {"answer": "totally wrong", "correct_self_assessment": False}
    monkeypatch.setattr(router, "complete_json", fake)
    c = sqlite3.connect(":memory:"); init_db(c)
    b_wrong = quizgen.estimate_difficulty({"question": "q", "answer_key": "x"}, conn=c, session_id="s")
    assert b_wrong > 0    # wrong by the weak student -> positive (harder) difficulty
