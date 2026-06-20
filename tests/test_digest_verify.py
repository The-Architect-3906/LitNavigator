import sqlite3
from litnav.storage.schema import init_db
from litnav.digest import verify
from litnav.digest.contract import VERIFY_THRESHOLD
from litnav.llm import router


def _edges():
    return [
        {"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
         "evidence": ["c0"], "max_strength": "explicit_assertion", "confidence": 0.75,
         "high_impact": True},
        {"prereq_slug": "a", "target_slug": "c", "edge_type": "prerequisite",
         "evidence": ["c1"], "max_strength": "weak_hint", "confidence": 0.55,
         "high_impact": False},   # below VERIFY_THRESHOLD -> downgraded
    ]


def test_low_confidence_edge_is_downgraded(monkeypatch):
    assert 0.55 < VERIFY_THRESHOLD
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": True, "a->c": True}
    out, unverified = verify.verify_edges(_edges(), judge_labels=labels, session_id="s", conn=c)
    a_c = [e for e in out if e["target_slug"] == "c"][0]
    assert a_c["edge_type"] == "similarity"          # downgraded
    assert a_c["verified"] is False
    assert any(e["target_slug"] == "c" for e in unverified)


def test_high_impact_edge_rejected_by_judge_is_downgraded(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": False, "a->c": True}            # judge rejects a->b
    out, unverified = verify.verify_edges(_edges(), judge_labels=labels, session_id="s", conn=c)
    a_b = [e for e in out if e["target_slug"] == "b"][0]
    assert a_b["edge_type"] == "similarity" and a_b["verified"] is False


def test_edge_accuracy_metric(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": True, "a->c": False}            # 1 of 2 prereq edges agreed
    acc = verify.edge_accuracy(_edges(), judge_labels=labels, session_id="s", conn=c)
    assert acc == 0.5


def test_judge_live_false_result_overrides_labels(monkeypatch):
    """Live complete_json returning {"is_prerequisite": False} downgrades even if the label says True."""
    monkeypatch.setattr(router, "complete_json", lambda *a, **kw: {"is_prerequisite": False})
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": True}
    edges = [{"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
              "evidence": ["c0"], "confidence": 0.75, "high_impact": True}]
    out, unverified = verify.verify_edges(edges, judge_labels=labels, session_id=None, conn=c)
    assert out[0]["edge_type"] == "similarity" and out[0]["verified"] is False


def test_judge_live_malformed_result_falls_back_to_labels(monkeypatch):
    """Live complete_json returning {} (no key) falls back to judge_labels (here False -> downgrade)."""
    monkeypatch.setattr(router, "complete_json", lambda *a, **kw: {})
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": False}
    edges = [{"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
              "evidence": ["c0"], "confidence": 0.75, "high_impact": True}]
    out, unverified = verify.verify_edges(edges, judge_labels=labels, session_id=None, conn=c)
    assert out[0]["edge_type"] == "similarity"
