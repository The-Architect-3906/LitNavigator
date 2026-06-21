"""UI open-world (live cold-start) wiring tests — offline/$0/deterministic.

The open-world build path (find-sources → digest) is exercised with monkeypatched discover +
a real digest over the offline fixture, so these run with provider=none at $0 and no network.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest import pipeline
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.ui.interactive import TutorSession, AgentSession


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Keep these tests offline/$0; restored after each test (no global pollution)."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")


def _seed_min_graph(conn) -> str:
    """Digest the offline fixture into `conn`, returning the topic/domain key."""
    fix = json.loads(Path("data/seed/digest_sources_fixture.json").read_text(encoding="utf-8"))
    di = DigestInput(fix["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in fix["sources"]], fix.get("target_slugs", []))
    pipeline.digest(di, conn=conn, candidate=fix["candidate"], session_id="t")
    return fix["domain_key"]


def test_start_accepts_goal_text():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    topic = _seed_min_graph(conn); repo.create_session(conn, "s1", topic=topic)
    tids = [r[0] for r in conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:2]
    ts = TutorSession(conn, ck, "s1")
    snap = ts.start(topic, target_concept_ids=tids, goal_text="quick overview", mastery_threshold=0.75)
    assert snap["route"]  # planned a route over the built graph


def test_open_world_build_streams_and_teaches(monkeypatch, tmp_path):
    fix = json.loads(Path("data/seed/digest_sources_fixture.json").read_text(encoding="utf-8"))
    src = fix["sources"][0]

    class _S:
        source_type, source_id, title, url = src["source_type"], src["source_id"], src["title"], src.get("url")
        # Long enough to pass the >200-char full-text gate; digest itself uses the fixture below.
        chunks = ["A sufficiently long discovered source chunk about the topic. " * 8]

    class _Res:
        sources = [_S()]

    from litnav.ui import interactive
    monkeypatch.setattr(interactive.find_sources, "find", lambda *a, **k: _Res())
    _orig_digest = interactive.pipeline.digest  # capture before patching to avoid recursion

    def _fake_digest(di, *, conn, candidate, session_id, budget=0):
        # Ignore the goal-built DigestInput; digest the deterministic fixture instead.
        return _orig_digest(
            DigestInput(fix["domain_key"],
                        [SourceDoc(src["source_type"], src["source_id"], src["title"],
                                   src.get("url"), src["chunks"])],
                        target_slugs=[]),
            conn=conn, candidate=fix["candidate"], session_id=session_id)

    monkeypatch.setattr(interactive.pipeline, "digest", _fake_digest)

    conn = sqlite3.connect(":memory:"); init_db(conn); repo.create_session(conn, "ow1", topic="g")
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    ag = AgentSession(conn, ck, "ow1", fixture_data=None,
                      open_world_goal="explain X", live=True, out_dir=str(tmp_path))
    assert ag.current().get("building") is True

    evs = list(ag.current_events())
    stages = [e["stage"] for e in evs if e.get("type") == "build"]
    assert "discover" in stages and "digest" in stages and "map" in stages
    assert any(e.get("type") in ("teach", "question") for e in evs)
    assert ag.built is True
    assert ag.concepts  # repopulated from the built graph


def test_open_world_no_source_is_graceful(monkeypatch, tmp_path):
    class _Res:
        sources = []
    from litnav.ui import interactive
    monkeypatch.setattr(interactive.find_sources, "find", lambda *a, **k: _Res())
    conn = sqlite3.connect(":memory:"); init_db(conn); repo.create_session(conn, "ow2", topic="g")
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    ag = AgentSession(conn, ck, "ow2", fixture_data=None,
                      open_world_goal="zzz nonsense", live=True, out_dir=str(tmp_path))
    evs = list(ag.current_events())
    assert any(e.get("kind") == "boundary" for e in evs)
    assert ag.built is False  # no graph built; honest decline, no crash


def test_start_agent_open_world_when_live(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    from litnav.ui import server
    sid = server._start_agent("teach me about quantum error correction", None)
    ag = server._AGENTS[sid]
    assert ag.open_world is True and ag.built is False
    assert ag.current().get("building") is True


def test_start_agent_curated_when_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from litnav.ui import server
    sid = server._start_agent("ReAct", None)
    assert server._AGENTS[sid].open_world is False
