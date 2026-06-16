import json
import sqlite3

from litnav.nodes.induce import induce_scaffold_node, induced_confidence
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_m3.json"
OFF = "multi_agent_debate"


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    repo.create_session(conn, "s", "agents")
    return conn


def _candidate():
    return json.loads(open(FIXTURE, encoding="utf-8").read())["induction"]


def test_induced_confidence_is_canonical_rule():
    assert induced_confidence(1, "weak_hint", False) == 0.55
    assert induced_confidence(1, "general_statement", False) == 0.65
    assert induced_confidence(1, "explicit_assertion", False) == 0.75
    assert induced_confidence(1, "explicit_assertion", True) == 0.85   # +multi_paper
    assert induced_confidence(3, "explicit_assertion", True) == 0.95   # 1.05 -> capped at 0.95


def test_off_skeleton_concept_absent_before_induction():
    conn = _conn()
    assert repo.get_concept_by_slug(conn, OFF) is None


def test_induce_writes_edge_misconception_log_and_route():
    conn = _conn()
    out = induce_scaffold_node({"session_id": "s", "route": [], "route_version": 1}, conn, _candidate())
    nid = out["current_concept_id"]

    edges = repo.get_induced_edges(conn)
    edge = next((e for e in edges if e["target_concept"] == nid), None)
    assert edge and edge["evidence"], "induced edge with cited evidence"

    mis = repo.get_misconceptions_for_concept(conn, nid)
    assert any(m["source"] == "induced" for m in mis), "induced misconception"

    log = repo.get_induction_log(conn, "s")
    assert {"prereq", "misconception"} <= {l["kind"] for l in log}
    assert all(l["confidence_basis"] for l in log), "confidence_basis logged for each"

    assert any(s["concept_id"] == nid for s in out["route"]), "induced concept slotted into route"

    concept = repo.get_concept_by_slug(conn, OFF)
    assert concept and concept["frontier_flag"] == "contested"


def test_trace_surfaces_induced_provenance():
    from litnav.ui.trace import build_trace
    conn = _conn()
    induce_scaffold_node({"session_id": "s", "route": [], "route_version": 1}, conn, _candidate())
    t = build_trace(conn, "s")
    assert t["induced_edges"], "induced edges surfaced in trace"
    kinds = {i["kind"] for i in t["induction"]}
    assert {"prereq", "misconception"} <= kinds
    assert all(i["confidence_basis"] for i in t["induction"])


def test_induced_edge_confidence_matches_rule_and_is_not_one():
    conn = _conn()
    out = induce_scaffold_node({"session_id": "s", "route": [], "route_version": 1}, conn, _candidate())
    nid = out["current_concept_id"]
    edge = next(e for e in repo.get_induced_edges(conn) if e["target_concept"] == nid)
    assert edge["confidence"] == induced_confidence(1, "explicit_assertion", False) == 0.75
    assert edge["confidence"] < 1.0  # induced never reaches full certainty
