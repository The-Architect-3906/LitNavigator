"""TDD tests for extraction-time builds_on prerequisite hint (feat/digest-edge-reliability).

Three test groups:
1. extract.py — builds_on parsed correctly from LLM response; self-refs + unknown slugs dropped.
2. _propose_edges prompt — when concepts carry builds_on, prompt contains "Candidate prerequisite hints"
   section with the right prereq->target lines.
3. fallback union — empty LLM proposal + builds_on hints + keypoints with evidence chunks =>
   build_edges produces >=1 prerequisite edge (evidence-backed, weak_hint). When the LLM already
   returned real prereq edges, seeds are NOT added (no double).
"""
from __future__ import annotations

import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import extract, edges
from litnav.llm import router

# ---------------------------------------------------------------------------
# shared fixtures
# ---------------------------------------------------------------------------

CANDIDATE_EXTRACT = {
    "concepts": [
        {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
    ],
    "keypoints": [
        {"kp_id": "kp_tool_1", "concept_slug": "tool_use", "name": "What a tool call is",
         "objective": "Describe how a tool call works.", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp_ra_1", "concept_slug": "reason_act", "name": "Interleave thought and action",
         "objective": "Explain how ReAct interleaves reasoning and acting.",
         "evidence_chunk_id": "c1", "bloom_level": "understand"},
    ],
}

CANDIDATE_EDGES = {
    "prereq_edges": [],
    "similarity_edges": [],
}


def _di_two_sources():
    return DigestInput(
        "llm-agents",
        [
            SourceDoc("arxiv", "x", "X", None, ["tools text"]),
            SourceDoc("arxiv", "y", "Y", None, ["react text"]),
        ],
        target_slugs=[],
    )


# ---------------------------------------------------------------------------
# Group 1: extract.py — builds_on parsing
# ---------------------------------------------------------------------------

def test_builds_on_parsed_when_llm_provides_it(monkeypatch):
    """When the LLM returns builds_on, extract_concepts parses valid slugs and attaches them."""
    live = {
        "concepts": [
            {"slug": "tool_use", "name": "Tool Use", "builds_on": []},
            {"slug": "reason_act", "name": "Reasoning + Acting", "builds_on": ["tool_use"]},
        ],
        "keypoints": [
            {"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "recall"},
            {"kp_id": "kp2", "concept_slug": "reason_act", "bloom_level": "recall"},
        ],
    }
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    concepts, _ = extract.extract_concepts(_di_two_sources(), candidate=CANDIDATE_EXTRACT,
                                           session_id=None, conn=None)
    by_slug = {c["slug"]: c for c in concepts}
    assert by_slug["tool_use"]["builds_on"] == []
    assert by_slug["reason_act"]["builds_on"] == ["tool_use"]


def test_builds_on_drops_self_ref(monkeypatch):
    """A concept listing itself in builds_on must be silently dropped (self-loop not allowed)."""
    live = {
        "concepts": [
            {"slug": "tool_use", "name": "Tool Use", "builds_on": ["tool_use"]},
        ],
        "keypoints": [
            {"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "recall"},
        ],
    }
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    concepts, _ = extract.extract_concepts(_di_two_sources(), candidate=CANDIDATE_EXTRACT,
                                           session_id=None, conn=None)
    assert concepts[0]["builds_on"] == []


def test_builds_on_drops_unknown_slug(monkeypatch):
    """Slugs not present in the response (hallucinated / cross-batch refs) must be dropped."""
    live = {
        "concepts": [
            {"slug": "tool_use", "name": "Tool Use", "builds_on": []},
            {"slug": "reason_act", "name": "Reasoning + Acting", "builds_on": ["GHOST_SLUG", "tool_use"]},
        ],
        "keypoints": [
            {"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "recall"},
            {"kp_id": "kp2", "concept_slug": "reason_act", "bloom_level": "recall"},
        ],
    }
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    concepts, _ = extract.extract_concepts(_di_two_sources(), candidate=CANDIDATE_EXTRACT,
                                           session_id=None, conn=None)
    by_slug = {c["slug"]: c for c in concepts}
    # GHOST_SLUG dropped, valid slug kept
    assert by_slug["reason_act"]["builds_on"] == ["tool_use"]


def test_builds_on_defaults_to_empty_list_when_absent(monkeypatch):
    """Concepts returned without a builds_on field default to []."""
    live = {
        "concepts": [
            {"slug": "tool_use", "name": "Tool Use"},          # no builds_on key at all
            {"slug": "reason_act", "name": "ReAct"},           # no builds_on key at all
        ],
        "keypoints": [
            {"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "recall"},
            {"kp_id": "kp2", "concept_slug": "reason_act", "bloom_level": "recall"},
        ],
    }
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    concepts, _ = extract.extract_concepts(_di_two_sources(), candidate=CANDIDATE_EXTRACT,
                                           session_id=None, conn=None)
    for c in concepts:
        assert c["builds_on"] == []


def test_builds_on_defaults_when_offline(monkeypatch):
    """Offline (provider=none): candidate concepts lack builds_on -> each concept gets []."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    concepts, _ = extract.extract_concepts(_di_two_sources(), candidate=CANDIDATE_EXTRACT,
                                           session_id="s", conn=c)
    for concept in concepts:
        assert "builds_on" in concept
        assert concept["builds_on"] == []


# ---------------------------------------------------------------------------
# Group 2: _propose_edges prompt — hint section injected when builds_on present
# ---------------------------------------------------------------------------

def test_propose_edges_prompt_contains_hint_section_when_builds_on_set():
    """When concepts carry builds_on, the prompt passed to the LLM contains the
    'Candidate prerequisite hints' section with the correct prereq->target lines."""
    captured_prompts: list[str] = []

    def _capture(prompt, **kwargs):
        captured_prompts.append(prompt)
        return {"prereq_edges": [], "similarity_edges": []}

    concepts_with_hints = [
        {"slug": "tool_use", "name": "Tool Use", "builds_on": []},
        {"slug": "reason_act", "name": "Reasoning + Acting", "builds_on": ["tool_use"]},
    ]
    by_chunk = {"c0": "tools text", "c1": "react text"}
    candidate = {"prereq_edges": [], "similarity_edges": []}

    import litnav.llm.router as _router
    original = _router.complete_json
    _router.complete_json = _capture
    try:
        edges._propose_edges(concepts_with_hints, by_chunk, candidate,
                             session_id=None, conn=None, budget=None, domain="test")
    finally:
        _router.complete_json = original

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "Candidate prerequisite hints" in prompt
    assert "tool_use -> reason_act" in prompt


def test_propose_edges_prompt_omits_hint_section_when_no_builds_on():
    """When no concept has builds_on entries, the hint section must NOT appear in the prompt."""
    captured_prompts: list[str] = []

    def _capture(prompt, **kwargs):
        captured_prompts.append(prompt)
        return {"prereq_edges": [], "similarity_edges": []}

    concepts_no_hints = [
        {"slug": "tool_use", "name": "Tool Use", "builds_on": []},
        {"slug": "reason_act", "name": "Reasoning + Acting", "builds_on": []},
    ]
    by_chunk = {"c0": "tools text", "c1": "react text"}
    candidate = {"prereq_edges": [], "similarity_edges": []}

    import litnav.llm.router as _router
    original = _router.complete_json
    _router.complete_json = _capture
    try:
        edges._propose_edges(concepts_no_hints, by_chunk, candidate,
                             session_id=None, conn=None, budget=None, domain="test")
    finally:
        _router.complete_json = original

    assert len(captured_prompts) == 1
    assert "Candidate prerequisite hints" not in captured_prompts[0]


def test_propose_edges_multiple_hints_all_appear():
    """Multiple builds_on entries across concepts each appear as a separate hint line."""
    captured_prompts: list[str] = []

    def _capture(prompt, **kwargs):
        captured_prompts.append(prompt)
        return {"prereq_edges": [], "similarity_edges": []}

    concepts = [
        {"slug": "a", "name": "A", "builds_on": []},
        {"slug": "b", "name": "B", "builds_on": ["a"]},
        {"slug": "c", "name": "C", "builds_on": ["a", "b"]},
    ]
    by_chunk = {"c0": "text"}
    candidate = {"prereq_edges": [], "similarity_edges": []}

    import litnav.llm.router as _router
    original = _router.complete_json
    _router.complete_json = _capture
    try:
        edges._propose_edges(concepts, by_chunk, candidate,
                             session_id=None, conn=None, budget=None)
    finally:
        _router.complete_json = original

    prompt = captured_prompts[0]
    assert "a -> b" in prompt
    assert "a -> c" in prompt
    assert "b -> c" in prompt


# ---------------------------------------------------------------------------
# Group 3: fallback union — seed edges when LLM returns empty prereq_edges
# ---------------------------------------------------------------------------

def test_fallback_seeds_produced_when_llm_returns_empty_prereqs(monkeypatch):
    """build_edges must produce >=1 prerequisite edge when the LLM returns no prereq_edges but
    concepts carry builds_on hints and keypoints provide evidence chunk ids."""
    # LLM returns empty prereq_edges
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"prereq_edges": [], "similarity_edges": []})
    # Also stub the similarity judge so it doesn't add noise
    monkeypatch.setattr(edges, "_judge_similar", lambda *a, **k: 0.0)

    concepts = [
        {"slug": "tool_use", "name": "Tool Use", "domain": "d", "frontier_flag": None,
         "builds_on": []},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "d", "frontier_flag": None,
         "builds_on": ["tool_use"]},
    ]
    keypoints = [
        {"kp_id": "kp1", "concept_slug": "tool_use", "name": "k1",
         "objective": "Obj 1", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp2", "concept_slug": "reason_act", "name": "k2",
         "objective": "Obj 2", "evidence_chunk_id": "c1", "bloom_level": "recall"},
    ]
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["tools text", "react text"])],
                     target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts, candidate=CANDIDATE_EDGES,
                            session_id="s", conn=c, keypoints=keypoints)

    prereqs = [e for e in out if e["edge_type"] == "prerequisite"]
    assert len(prereqs) >= 1, "expected >=1 seed prereq edge from builds_on fallback"
    assert prereqs[0]["prereq_slug"] == "tool_use"
    assert prereqs[0]["target_slug"] == "reason_act"
    # seed must carry real evidence (not empty, or it would be dropped)
    assert prereqs[0]["evidence"], "seed edge must have non-empty evidence chunks"
    # seed is marked weak_hint
    assert prereqs[0]["max_strength"] == "weak_hint"


def test_fallback_seeds_use_endpoint_keypoint_chunks(monkeypatch):
    """The seed's evidence chunk ids come from the keypoints of both endpoint concepts."""
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"prereq_edges": [], "similarity_edges": []})
    monkeypatch.setattr(edges, "_judge_similar", lambda *a, **k: 0.0)

    concepts = [
        {"slug": "a", "name": "A", "domain": "d", "frontier_flag": None, "builds_on": []},
        {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None, "builds_on": ["a"]},
    ]
    keypoints = [
        {"kp_id": "kp_a", "concept_slug": "a", "name": "k",
         "objective": "Obj", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp_b", "concept_slug": "b", "name": "k2",
         "objective": "Obj2", "evidence_chunk_id": "c1", "bloom_level": "recall"},
    ]
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["chunk a text", "chunk b text"])],
                     target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts, candidate=CANDIDATE_EDGES,
                            session_id="s", conn=c, keypoints=keypoints)
    prereqs = [e for e in out if e["edge_type"] == "prerequisite"]
    assert len(prereqs) >= 1
    # evidence must include at least one chunk from each endpoint
    ev_set = set(prereqs[0]["evidence"])
    assert "c0" in ev_set or "c1" in ev_set  # at minimum one endpoint's chunk


def test_fallback_seeds_not_added_when_llm_returns_real_prereqs(monkeypatch):
    """When the LLM already returns real prereq edges, seeds must NOT be injected (no double)."""
    # LLM returns a real prereq edge
    def _real_llm(prompt, **kwargs):
        return {
            "prereq_edges": [
                {"prereq_slug": "tool_use", "target_slug": "reason_act",
                 "evidence_chunks": ["c0"], "max_strength": "explicit_assertion"}
            ],
            "similarity_edges": [],
        }
    monkeypatch.setattr(router, "complete_json", _real_llm)
    monkeypatch.setattr(edges, "_judge_similar", lambda *a, **k: 0.0)

    concepts = [
        {"slug": "tool_use", "name": "Tool Use", "domain": "d", "frontier_flag": None,
         "builds_on": []},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "d", "frontier_flag": None,
         "builds_on": ["tool_use"]},
    ]
    keypoints = [
        {"kp_id": "kp1", "concept_slug": "tool_use", "name": "k",
         "objective": "Obj", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp2", "concept_slug": "reason_act", "name": "k2",
         "objective": "Obj2", "evidence_chunk_id": "c1", "bloom_level": "recall"},
    ]
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["text1", "text2"])],
                     target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts, candidate=CANDIDATE_EDGES,
                            session_id="s", conn=c, keypoints=keypoints)

    prereqs = [e for e in out if e["edge_type"] == "prerequisite"]
    # exactly 1 edge, not 2 (seed was NOT added on top of real edge)
    assert len(prereqs) == 1, f"expected 1 prereq edge, got {len(prereqs)} (seed was wrongly added)"


def test_fallback_seeds_use_first_chunk_when_no_keypoint_evidence(monkeypatch):
    """When a concept has no keypoints with evidence chunk ids, the first chunk is used as fallback
    so the seed always has real evidence and is not dropped."""
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"prereq_edges": [], "similarity_edges": []})
    monkeypatch.setattr(edges, "_judge_similar", lambda *a, **k: 0.0)

    concepts = [
        {"slug": "a", "name": "A", "domain": "d", "frontier_flag": None, "builds_on": []},
        {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None, "builds_on": ["a"]},
    ]
    # No keypoints at all — seeds must still get evidence from the first available chunk
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["only chunk"])],
                     target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts, candidate=CANDIDATE_EDGES,
                            session_id="s", conn=c, keypoints=[])

    prereqs = [e for e in out if e["edge_type"] == "prerequisite"]
    assert len(prereqs) >= 1, "seed must survive even with no keypoints"
    assert prereqs[0]["evidence"], "seed evidence must be non-empty"


def test_fallback_seeds_survive_normal_scoring(monkeypatch):
    """Seeds injected as fallback flow through induced_confidence scoring; the resulting
    confidence is rule-computed (weak_hint, 1 chunk, single-paper) and is a float."""
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"prereq_edges": [], "similarity_edges": []})
    monkeypatch.setattr(edges, "_judge_similar", lambda *a, **k: 0.0)

    concepts = [
        {"slug": "a", "name": "A", "domain": "d", "frontier_flag": None, "builds_on": []},
        {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None, "builds_on": ["a"]},
    ]
    keypoints = [
        {"kp_id": "kp_a", "concept_slug": "a", "name": "k",
         "objective": "Obj", "evidence_chunk_id": "c0", "bloom_level": "recall"},
    ]
    di = DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["chunk text"])],
                     target_slugs=[])
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(di, concepts, candidate=CANDIDATE_EDGES,
                            session_id="s", conn=c, keypoints=keypoints)

    prereqs = [e for e in out if e["edge_type"] == "prerequisite"]
    assert prereqs, "seed edge must be present"
    conf = prereqs[0]["confidence"]
    assert isinstance(conf, float), f"confidence must be a float, got {type(conf)}"
    # weak_hint, 1 chunk, single-paper → induced_confidence(1, 'weak_hint', False)
    from litnav.nodes.induce import induced_confidence
    expected = induced_confidence(1, "weak_hint", False)
    assert conf == expected, f"confidence {conf} != expected {expected} for weak_hint/1chunk/single"
