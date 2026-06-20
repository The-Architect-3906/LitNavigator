import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import edges


CONCEPTS = [
    {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
    {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
]
CANDIDATE = {
    "prereq_edges": [
        {"prereq_slug": "tool_use", "target_slug": "reason_act",
         "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False},
    ],
    "similarity_edges": [
        {"a_slug": "tool_use", "b_slug": "reason_act",
         "evidence_chunks": ["c0", "c1"], "max_strength": "general_statement", "multi_paper": True},
    ],
}


def _input(targets=None):
    return DigestInput("llm-agents",
                       [SourceDoc("arxiv", "x", "X", None, ["c0 text", "c1 text"])],
                       target_slugs=targets or [])


def test_prereq_edge_confidence_is_rule_computed(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(), CONCEPTS, candidate=CANDIDATE, session_id="s", conn=c)
    prereq = [e for e in out if e["edge_type"] == "prerequisite"]
    assert len(prereq) == 1
    assert prereq[0]["confidence"] == 0.75          # 1 chunk, explicit, single
    assert prereq[0]["high_impact"] is True          # target_slugs=[] -> all impactful


def test_similarity_edge_confidence_is_rule_computed(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(), CONCEPTS, candidate=CANDIDATE, session_id="s", conn=c)
    sim = [e for e in out if e["edge_type"] == "similarity"]
    assert len(sim) == 1
    assert sim[0]["confidence"] == 0.90              # 2 chunks, general, multi
    assert sim[0]["high_impact"] is False            # similarity edges are never high-impact


def test_high_impact_only_for_targeted_slice(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_input(targets=["tool_use"]), CONCEPTS, candidate=CANDIDATE,
                            session_id="s", conn=c)
    prereq = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert prereq["high_impact"] is False            # reason_act not in targets


def test_similarity_cosine_filter_drops_far_pairs(monkeypatch):
    """Live path: similarity pairs below _SIM_COS_MIN are dropped; pairs at/above are kept."""
    from litnav.llm import router as _router
    concepts3 = [
        {"slug": "a", "name": "A", "domain": "d", "frontier_flag": None},
        {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None},
        {"slug": "c", "name": "C", "domain": "d", "frontier_flag": None},
    ]
    vecs = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]  # cos(a,b)=1.0 keep ; cos(a,c)=0.0 drop
    monkeypatch.setattr(_router, "embed_texts", lambda *a, **k: vecs)
    candidate = {"prereq_edges": [], "similarity_edges": [
        {"a_slug": "a", "b_slug": "b", "evidence_chunks": ["c0"], "max_strength": "weak_hint", "multi_paper": False},
        {"a_slug": "a", "b_slug": "c", "evidence_chunks": ["c0"], "max_strength": "weak_hint", "multi_paper": False},
    ]}
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["text"])], target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts3, candidate=candidate, session_id="s", conn=c)
    sim = [e for e in out if e["edge_type"] == "similarity"]
    assert len(sim) == 1 and sim[0]["prereq_slug"] == "a" and sim[0]["target_slug"] == "b"


def test_edges_skip_unknown_slugs(monkeypatch):
    """Edges referencing a slug not present in `concepts` are skipped (both edge types)."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    concepts1 = [{"slug": "tool_use", "name": "Tool Use", "domain": "d", "frontier_flag": None}]
    candidate = {"prereq_edges": [
        {"prereq_slug": "tool_use", "target_slug": "GHOST", "evidence_chunks": ["c0"],
         "max_strength": "explicit_assertion", "multi_paper": False}],
        "similarity_edges": [
        {"a_slug": "tool_use", "b_slug": "GHOST", "evidence_chunks": ["c0"],
         "max_strength": "general_statement", "multi_paper": False}]}
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["text"])], target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts1, candidate=candidate, session_id="s", conn=c)
    assert out == []   # both edges skipped (GHOST not a known concept)
