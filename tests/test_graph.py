import sqlite3
import uuid

from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.graph_svg import to_svg
from litnav.ui.trace import build_trace, concept_graph

FIXTURE = "data/seed/agents_m3.json"


def _conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    return conn


def test_base_graph_has_all_concepts_and_curated_edges():
    g = concept_graph(_conn(), session_id=None)
    assert len(g["nodes"]) == 7
    assert len(g["edges"]) == 6  # react->{2,3,4,6,7}, reflection->5
    assert all(n["state"] == "idle" and not n["induced"] for n in g["nodes"])
    assert all(e["source"] == "curated" for e in g["edges"])


def test_to_svg_renders_without_dependency():
    svg = to_svg(concept_graph(_conn(), None))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "ReAct" in svg  # a node label made it in


def test_concept_graph_includes_similarity_edges_tagged():
    """Similarity ('related') edges must reach the map, distinct from prerequisites — the digest
    classifies most cross-concept links as similarity, and dropping them leaves a near-edgeless map."""
    from litnav.storage import repo
    conn = _conn()
    repo.record_edge(conn, 2, 3, edge_type="similarity", source="digested",
                     confidence=0.8, evidence_chunks=[], slice_key="t")
    g = concept_graph(conn, session_id=None)
    kinds = [e.get("kind") for e in g["edges"]]
    assert kinds.count("prerequisite") == 6
    sim = [e for e in g["edges"] if e.get("kind") == "similarity"]
    assert len(sim) == 1
    assert {sim[0]["prereq_id"], sim[0]["target_id"]} == {2, 3}


def test_similarity_edge_not_used_for_layering():
    """A similarity edge is not a precedence relation — it must not push a node into a later column."""
    from litnav.ui.graph_svg import _layers
    nodes = [{"id": 1}, {"id": 2}]
    sim = [{"prereq_id": 1, "target_id": 2, "source": "digested", "kind": "similarity"}]
    layer = _layers(nodes, sim)
    assert layer[1] == 0 and layer[2] == 0


def test_similarity_pair_already_prereq_is_not_duplicated():
    """If a pair is already a prerequisite edge, the similarity duplicate is dropped (no double line)."""
    from litnav.storage import repo
    conn = _conn()
    # 1->2 is a curated prerequisite in the fixture; a similarity over the same pair must be dropped.
    repo.record_edge(conn, 1, 2, edge_type="similarity", source="digested",
                     confidence=0.8, evidence_chunks=[], slice_key="t")
    g = concept_graph(conn, None)
    assert not any(e.get("kind") == "similarity" for e in g["edges"])


def test_to_svg_renders_similarity_distinct_from_prereq():
    from litnav.storage import repo
    conn = _conn()
    repo.record_edge(conn, 2, 3, edge_type="similarity", source="digested",
                     confidence=0.8, evidence_chunks=[], slice_key="t")
    svg = to_svg(concept_graph(conn, None))
    assert "marker-end='url(#arw)'" in svg     # prerequisites keep the directed arrow
    assert "<line" in svg                       # similarity drawn as an undirected line
    assert "stroke-dasharray='2 4'" in svg      # similarity uses a dotted style


def test_session_graph_quiz_posed_after_teach_phase():
    """After teaching all keypoints, the graph poses a quiz (assess phase starts)."""
    from litnav.ui.interactive import TutorSession
    conn = _conn()
    sid = str(uuid.uuid4())
    ts = TutorSession(conn, sqlite3.connect(":memory:", check_same_thread=False), sid)
    snap = ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)
    # After start(), all keypoints are taught and a quiz should be pending
    assert snap.get("question"), "a quiz must be posed after the TEACH phase completes"


def test_glassbox_meaningful_at_first_pause_then_fills():
    """The advisor's concern: build_trace must return usable data on a paused live session,
    and grow each turn. Drive a TutorSession to its first post-check pause, then one answer."""
    from litnav.ui.interactive import TutorSession
    conn = _conn()
    sid = str(uuid.uuid4())
    ts = TutorSession(conn, sqlite3.connect(":memory:", check_same_thread=False), sid)
    ts.start("agents", target_concept_ids=[1], mastery_threshold=0.75)

    # At the first pause: route + concepts are already persisted; no decision yet.
    t0 = build_trace(conn, sid)
    assert t0["route"], "route written before the first pause"
    assert t0["concepts"], "learner_state seeded before the first pause"
    assert t0["timeline"] == []

    # Answer that explicitly contains the kp_react_2 recall answer_key phrase
    ts.answer("it uses actions and observations from the environment unlike CoT")
    t1 = build_trace(conn, sid)
    assert t1["timeline"], "a graded turn (reteach or advance) appears after the first answer"
    assert t1["decisions"], "a routing decision is recorded after the first answer"
