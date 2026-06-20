import sqlite3
from litnav.storage.schema import init_db
from litnav.digest import verify
from litnav.llm import router

def test_judge_called_once_per_high_impact_edge(monkeypatch):
    calls = {"n": 0}
    def fake(*a, **k):
        calls["n"] += 1
        return {"is_prerequisite": True}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai"); monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(router, "complete_json", fake)
    edges = [{"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
              "evidence": ["c0"], "confidence": 0.75, "high_impact": True}]
    c = sqlite3.connect(":memory:"); init_db(c)
    acc, (out, unverified) = verify.verify_pass(edges, judge_labels={}, session_id="s", conn=c)
    assert calls["n"] == 1            # judged exactly once (not twice)
    assert acc == 1.0 and out[0]["edge_type"] == "prerequisite" and out[0]["verified"] is True

def test_verify_pass_accuracy_over_all_prereq_edges(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    edges = [
        {"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
         "evidence": ["c0"], "confidence": 0.75, "high_impact": True},     # judged True (label)
        {"prereq_slug": "a", "target_slug": "c", "edge_type": "prerequisite",
         "evidence": ["c1"], "confidence": 0.55, "high_impact": False},    # low-conf -> downgraded
    ]
    labels = {"a->b": True, "a->c": False}
    acc, (out, unverified) = verify.verify_pass(edges, judge_labels=labels, session_id="s", conn=c)
    assert acc == 0.5                  # 1 of 2 proposed prereq edges judged genuine
    assert len(unverified) == 1 and unverified[0]["target_slug"] == "c"


def test_refd_rescues_judge_rejected_high_impact_edge(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    import sqlite3
    from litnav.storage.schema import init_db
    c = sqlite3.connect(":memory:"); init_db(c)
    edges = [{"prereq_slug": "b", "target_slug": "a", "edge_type": "prerequisite",
              "evidence": ["c0"], "confidence": 0.75, "high_impact": True}]
    labels = {"b->a": False}                      # judge REJECTS
    refd = {("b", "a"): 0.5}                       # but RefD strongly corroborates
    acc, (out, unverified) = verify.verify_pass(edges, judge_labels=labels, session_id="s", conn=c, refd=refd)
    assert out[0]["edge_type"] == "prerequisite"  # RefD rescued it (kept, not downgraded)
    assert out[0]["verified"] is True
