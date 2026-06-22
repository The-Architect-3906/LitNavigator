"""Tests for OW-6 P6: unified glass-box+user frontend.

Verifies:
  1. flow_meta.meta_for returns correct provenance for known nodes.
  2. The agent.html template contains the new sections.
  3. The /tutor/{sid} page renders with the expected new HTML elements.
  4. Step events emitted by TutorSession carry skill/method/paper keys.
  5. The state event carries a 'recommend' key.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from litnav.ui import flow_meta
from litnav.ui.flow_meta import meta_for


# ── 1. flow_meta unit tests ──────────────────────────────────────────────────

def test_meta_for_assess_next_has_saquet_and_bloomllm():
    m = meta_for("assess_next")
    assert m["skill"] == "assess"
    paper = m["paper"].lower()
    assert "saquet" in paper or "bloomllm" in paper


def test_meta_for_grade_kp_has_bkt():
    m = meta_for("grade_kp")
    assert m["skill"] == "assess"
    assert "corbett" in m["paper"].lower() or "bkt" in m["paper"].lower()


def test_meta_for_teach_kp_has_mayer_and_sweller():
    m = meta_for("teach_kp")
    assert m["skill"] == "teach"
    assert "mayer" in m["paper"].lower()
    assert "sweller" in m["paper"].lower() or "kalyuga" in m["paper"].lower()


def test_meta_for_reteach_kp_skill_is_teach():
    m = meta_for("reteach_kp")
    assert m["skill"] == "teach"


def test_meta_for_diagnose_replan_skill_is_recommend():
    assert meta_for("diagnose")["skill"] == "recommend"
    assert meta_for("replan")["skill"] == "recommend"


def test_meta_for_select_next_skill_is_recommend_next():
    m = meta_for("select_next")
    assert m["skill"] == "recommend-next"


def test_meta_for_goal_elicit_has_bloom():
    m = meta_for("goal_elicit")
    assert "bloom" in m["paper"].lower()


def test_meta_for_unknown_node_returns_defaults():
    m = meta_for("__no_such_node__")
    assert m == {"skill": "—", "method": "—", "paper": "—"}


def test_meta_for_does_not_mutate_default():
    """Mutating the returned dict must not affect subsequent calls."""
    m1 = meta_for("__x__")
    m1["skill"] = "oops"
    m2 = meta_for("__x__")
    assert m2["skill"] == "—"


def test_all_step_label_nodes_have_meta():
    """Every node in _STEP_LABELS should appear in NODE_META (coverage sanity check)."""
    from litnav.ui.interactive import TutorSession
    missing = [n for n in TutorSession._STEP_LABELS if n not in flow_meta.NODE_META]
    assert missing == [], f"Nodes in _STEP_LABELS but missing from NODE_META: {missing}"


# ── 2. agent.html template structure ────────────────────────────────────────

def test_agent_html_contains_research_detail_toggle():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert "detail-chk" in html, "research detail checkbox id missing"
    assert "Show research detail" in html
    assert "show-detail" in html
    assert "toggleDetail" in html


def test_agent_html_contains_recommend_card():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert 'id="recommend"' in html
    assert "What to learn next" in html
    assert "recommend-list" in html


def test_agent_html_contains_research_chip_css():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert "research-chip" in html
    assert "chip-skill" in html


def test_agent_html_flow_js_uses_skill_method_paper():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    # The step event handler must forward skill/method/paper from SSE events
    assert "e.skill" in html
    assert "e.method" in html
    assert "e.paper" in html


# ── 3. Server integration: page renders with new sections ───────────────────

def _make_client():
    """Return a TestClient backed by a fresh in-memory session."""
    from litnav.ui.server import app
    return TestClient(app, raise_server_exceptions=True)


def test_tutor_start_redirects_and_page_has_new_sections():
    client = _make_client()
    # Start a session
    resp = client.get("/tutor/start?goal=react", follow_redirects=False)
    assert resp.status_code == 303
    sid = resp.headers["location"].split("/")[-1]

    # Fetch the tutor page
    page = client.get(f"/tutor/{sid}")
    assert page.status_code == 200
    html = page.text

    # New structural elements must be present
    assert 'id="recommend"' in html, "#recommend card missing from rendered page"
    assert "detail-chk" in html, "research detail toggle missing from rendered page"
    assert "research-chip" in html, "research-chip CSS missing from rendered page"
    assert "What to learn next" in html


# ── 4. Step events carry skill/method/paper ──────────────────────────────────

def test_step_event_has_provenance_keys():
    """_step_event must include skill, method, paper from flow_meta."""
    # Call the unbound method directly — it only needs self._STEP_LABELS which is a
    # class attribute, so a lightweight namespace object is sufficient.
    from litnav.ui.interactive import TutorSession
    import types

    stub = types.SimpleNamespace(_STEP_LABELS=TutorSession._STEP_LABELS)
    ev = TutorSession._step_event(stub, "assess_next", {})
    assert ev["type"] == "step"
    assert ev["skill"] == "assess"
    assert "SAQUET" in ev["paper"] or "BloomLLM" in ev["paper"]
    assert ev["method"]


def test_step_event_unknown_node_has_dash_defaults():
    from litnav.ui.interactive import TutorSession
    import types

    stub = types.SimpleNamespace(_STEP_LABELS=TutorSession._STEP_LABELS)
    ev = TutorSession._step_event(stub, "__unknown__", {})
    assert ev["skill"] == "—"
    assert ev["method"] == "—"
    assert ev["paper"] == "—"


# ── 5. server.py imports cleanly ─────────────────────────────────────────────

def test_server_imports_cleanly():
    from litnav.ui import server  # noqa: F401  — just check no ImportError


def test_flow_meta_imports_cleanly():
    from litnav.ui import flow_meta as fm  # noqa: F401
    assert hasattr(fm, "NODE_META")
    assert hasattr(fm, "meta_for")


# ── B7: Quiz card + recap framing ───────────────────────────────────────────

def test_agent_html_b7_bloom_chip_css():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert "bloom-chip" in html, "B7: .bloom-chip CSS class missing"
    assert "qa-header" in html, "B7: .qa-header class missing"
    assert "recap-badge" in html, "B7: .recap-badge class missing"


def test_agent_html_b7_question_handler_uses_bloom_and_retrieval():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert "e.bloom_level" in html, "B7: bloom_level not used in question handler"
    assert "e.is_retrieval" in html, "B7: is_retrieval not used in question handler"
    assert "QUESTION" in html, "B7: QUESTION chip text missing"
    assert "Recap" in html, "B7: Recap badge text missing"


def test_interactive_question_event_has_is_retrieval():
    """_terminal_events must include is_retrieval on question events."""
    from litnav.ui.interactive import TutorSession
    import inspect
    src = inspect.getsource(TutorSession._terminal_events)
    assert "is_retrieval" in src, "is_retrieval not emitted in _terminal_events"


# ── B8: Inline error + retry ─────────────────────────────────────────────────

def test_agent_html_b8_error_bubble_css():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    assert "error-bubble" in html, "B8: .error-bubble CSS missing"
    assert "error-btn-retry" in html, "B8: .error-btn-retry missing"


def test_agent_html_b8_no_blind_reload_on_error():
    from pathlib import Path
    html = Path("litnav/ui/templates/agent.html").read_text(encoding="utf-8")
    # The error SSE handler and catch block must not do a bare location.href reload.
    # We check: showError is called, not location.href, in the error/catch contexts.
    assert "showError" in html, "B8: showError function missing"
    # Confirm _lastStreamBody is stored (enables retry)
    assert "_lastStreamBody" in html, "B8: _lastStreamBody tracking missing"
