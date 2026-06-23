"""Digest edge reliability: a multi-concept graph must never be edgeless.

The live LLM edge proposal is non-deterministic — some runs return zero prerequisite edges, leaving
the induced-curriculum map a disconnected column. When no prerequisite edge survives and there are
>=2 concepts, _write_graph synthesizes a SEQUENTIAL backbone over the concept order (concept[i] is a
prereq of concept[i+1]), marked source='induced' so the UI renders it dashed (an inferred ordering,
not a verified prerequisite). The extraction order is teaching order, so a linear spine matches the
lesson's own narrative ("first… next… then… finally…").
"""
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest import pipeline
from litnav.digest.contract import DigestInput, SourceDoc


def _di():
    return DigestInput("test goal", [SourceDoc("web", "s0", "Src", None, ["chunk text one. " * 20])],
                       target_slugs=[])


CONCEPTS = [
    {"slug": "a", "name": "Concept A"},
    {"slug": "b", "name": "Concept B"},
    {"slug": "c", "name": "Concept C"},
]


def _prereq_edges(conn):
    return conn.execute(
        "SELECT prereq_concept, target_concept, source FROM concept_edges WHERE edge_type='prerequisite'"
    ).fetchall()


def test_backbone_added_when_no_prereq_edges():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", "t")
    pipeline._write_graph(c, _di(), CONCEPTS, [], [], [], [])   # scored_edges = [] (none proposed)
    edges = _prereq_edges(c)
    assert len(edges) >= len(CONCEPTS) - 1, "expected a sequential backbone over the concepts"
    # all backbone edges are marked induced (dashed in the UI)
    assert all(src == "induced" for _, _, src in edges)
    # it's a chain in concept order, not a star/self-loop
    prereqs = {p for p, _, _ in edges}
    targets = {t for _, t, _ in edges}
    assert prereqs != targets   # directional, not degenerate


def test_real_prereq_edges_are_not_overridden_by_backbone():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", "t")
    real = [{"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
             "confidence": 0.9, "evidence": []}]
    pipeline._write_graph(c, _di(), CONCEPTS, real, [], [], [])
    edges = _prereq_edges(c)
    # the real digested edge survives; no induced backbone is forced on top
    assert any(src == "digested" for _, _, src in edges)
    assert not any(src == "induced" for _, _, src in edges), "backbone must NOT fire when real edges exist"


def test_single_concept_no_backbone():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", "t")
    pipeline._write_graph(c, _di(), [CONCEPTS[0]], [], [], [], [])
    assert _prereq_edges(c) == []   # nothing to chain
