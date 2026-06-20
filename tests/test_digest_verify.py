import sqlite3
from litnav.storage.schema import init_db
from litnav.digest import verify
from litnav.digest.contract import VERIFY_THRESHOLD


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
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    labels = {"a->b": True, "a->c": True}
    out, unverified = verify.verify_edges(_edges(), judge_labels=labels, session_id="s", conn=c)
    a_c = [e for e in out if e["target_slug"] == "c"][0]
    assert 0.55 < VERIFY_THRESHOLD
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
