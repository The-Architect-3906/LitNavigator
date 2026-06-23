"""Tests for _live_story_context — glass-box story band reflects live session data.

The bug: tutor_page always rendered _story_context(_fixture_data()), so live open-world
sessions showed the static offline agents fixture (ReAct, Toolformer, …) even when
teaching an unrelated topic (e.g. CRISPR). Fix: _live_story_context(ag) queries the
per-session DB for real concept names and paper titles.
"""
import sqlite3

import pytest

from litnav.storage.schema import init_db
from litnav.ui.server import _live_story_context


class _FakeAgent:
    """Minimal stub with the fields _live_story_context needs."""

    def __init__(self, conn, goal: str):
        self.conn = conn
        self.goal = goal
        self.topic = goal
        self.open_world = True


def _make_db_with_data(goal: str, concept_names: list[str], paper_titles: list[str]):
    """Create an in-memory DB, init schema, insert concepts + papers, return (conn, agent)."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    for i, name in enumerate(concept_names):
        slug = name.lower().replace(" ", "-")
        conn.execute(
            "INSERT INTO concepts (slug, name) VALUES (?, ?)", (slug, name)
        )

    for i, title in enumerate(paper_titles):
        conn.execute(
            "INSERT INTO papers (title, year) VALUES (?, ?)", (title, 2024 + i)
        )

    conn.commit()
    ag = _FakeAgent(conn, goal)
    return conn, ag


# ── Core correctness ────────────────────────────────────────────────────────


def test_live_story_context_returns_real_concepts():
    concepts = ["Gene Editing", "CRISPR-Cas9", "Off-target Effects"]
    papers = ["Doudna 2012", "Anzalone 2019"]
    _conn, ag = _make_db_with_data("CRISPR gene editing", concepts, papers)

    ctx = _live_story_context(ag)

    assert ctx["story_concept_count"] == 3
    assert ctx["story_concept_names"] == concepts
    assert ctx["story_target_names"] == concepts[:4]  # first-4 slice


def test_live_story_context_returns_real_paper_count():
    concepts = ["Gene Editing", "CRISPR-Cas9", "Off-target Effects"]
    papers = ["Doudna 2012", "Anzalone 2019"]
    _conn, ag = _make_db_with_data("CRISPR gene editing", concepts, papers)

    ctx = _live_story_context(ag)

    assert ctx["story_paper_count"] == 2
    assert len(ctx["story_representative_papers"]) == 2
    rep_titles = [p["title"] for p in ctx["story_representative_papers"]]
    assert rep_titles == papers


def test_live_story_context_does_not_contain_fixture_content():
    """The live context must not bleed in any content from the static agents fixture."""
    concepts = ["Gene Editing", "CRISPR-Cas9", "Off-target Effects"]
    papers = ["Doudna 2012", "Anzalone 2019"]
    _conn, ag = _make_db_with_data("CRISPR gene editing", concepts, papers)

    ctx = _live_story_context(ag)

    all_text = " ".join([
        ctx["story_domain"],
        " ".join(ctx["story_concept_names"]),
        " ".join(p["title"] for p in ctx["story_representative_papers"]),
    ])
    for fixture_term in ("ReAct", "Toolformer", "Reflexion", "MetaGPT", "autonomous agents"):
        assert fixture_term not in all_text, (
            f"Fixture term {fixture_term!r} leaked into live story context"
        )


def test_live_story_context_uses_goal_as_domain():
    _conn, ag = _make_db_with_data("CRISPR gene editing", ["A"], ["P1"])
    ctx = _live_story_context(ag)
    assert ctx["story_domain"] == "CRISPR gene editing"


def test_live_story_context_edge_count_zero_on_empty_graph():
    """No concept_edges in session → edge_count is 0, no crash."""
    _conn, ag = _make_db_with_data("test goal", ["C1", "C2"], ["P1"])
    ctx = _live_story_context(ag)
    assert ctx["story_edge_count"] == 0


def test_live_story_context_edge_count_populated():
    concepts = ["A", "B"]
    _conn, ag = _make_db_with_data("test goal", concepts, ["P1"])
    # Insert a concept edge
    _conn.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (1, 2, 'prerequisite')"
    )
    _conn.commit()
    ctx = _live_story_context(ag)
    assert ctx["story_edge_count"] == 1


def test_live_story_context_empty_db():
    """No concepts/papers — returns zeros, no crash."""
    _conn, ag = _make_db_with_data("sparse topic", [], [])
    ctx = _live_story_context(ag)
    assert ctx["story_concept_count"] == 0
    assert ctx["story_paper_count"] == 0
    assert ctx["story_representative_papers"] == []
    assert ctx["story_concept_names"] == []


def test_live_story_context_representative_papers_capped_at_5():
    """When there are more than 5 papers, only 5 appear as representative."""
    papers = [f"Paper {i}" for i in range(8)]
    _conn, ag = _make_db_with_data("many papers", ["C1"], papers)
    ctx = _live_story_context(ag)
    assert len(ctx["story_representative_papers"]) == 5
    assert ctx["story_paper_count"] == 8  # total count is still accurate


# ── Key dict shape ──────────────────────────────────────────────────────────

_REQUIRED_KEYS = {
    "story_domain",
    "story_paper_count",
    "story_representative_papers",
    "story_concept_count",
    "story_edge_count",
    "story_target_names",
    "story_concept_names",
}


def test_live_story_context_has_required_keys():
    _conn, ag = _make_db_with_data("topic", ["C1"], ["P1"])
    ctx = _live_story_context(ag)
    missing = _REQUIRED_KEYS - set(ctx.keys())
    assert not missing, f"Missing keys: {missing}"
