import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import extract
from litnav.llm import router


CANDIDATE = {
    "concepts": [
        {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": "consensus"},
    ],
    "keypoints": [
        {"kp_id": "kp_tool_1", "concept_slug": "tool_use", "name": "What a tool call is",
         "objective": "define tool use", "evidence_chunk_id": "c0", "bloom_level": "recall"},
        {"kp_id": "kp_ra_1", "concept_slug": "reason_act", "name": "Interleave thought and action",
         "objective": "explain ReAct", "evidence_chunk_id": "c1", "bloom_level": "understand"},
    ],
}


def _input():
    return DigestInput(
        domain_key="llm-agents",
        sources=[SourceDoc("arxiv", "2302.04761", "Toolformer", None, ["tools text", "react text"])],
        target_slugs=[],
    )


def test_offline_replays_candidate(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    concepts, keypoints = extract.extract_concepts(_input(), candidate=CANDIDATE,
                                                   session_id="s", conn=c)
    assert {x["slug"] for x in concepts} == {"tool_use", "reason_act"}
    assert {k["kp_id"] for k in keypoints} == {"kp_tool_1", "kp_ra_1"}
    slugs = {x["slug"] for x in concepts}
    assert all(k["concept_slug"] in slugs for k in keypoints)


def test_offline_is_zero_cost(monkeypatch):
    from litnav.storage import cost_repo
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    extract.extract_concepts(_input(), candidate=CANDIDATE, session_id="s", conn=c)
    assert cost_repo.session_spend(c, "s")["tokens"] == 0


def test_partial_slug_filter_drops_invalid(monkeypatch):
    """Live: LLM returns 3 concepts, 1 with a blank slug -> only the 2 valid survive (no wholesale fallback)."""
    live = {"concepts": [{"slug": "tool_use", "name": "Tool Use"},
                         {"slug": "  ", "name": "Bad"},
                         {"slug": "reason_act", "name": "ReAct"}],
            "keypoints": [{"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "apply"}]}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    concepts, _ = extract.extract_concepts(_input(), candidate=CANDIDATE, session_id=None, conn=None)
    assert {c["slug"] for c in concepts} == {"tool_use", "reason_act"}


def test_orphan_keypoints_dropped(monkeypatch):
    """Live: a keypoint referencing a slug not in the accepted concept set is dropped."""
    live = {"concepts": [{"slug": "tool_use", "name": "Tool Use"}],
            "keypoints": [{"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "recall"},
                          {"kp_id": "kp2", "concept_slug": "GHOST_SLUG", "bloom_level": "recall"}]}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    _, keypoints = extract.extract_concepts(_input(), candidate=CANDIDATE, session_id=None, conn=None)
    assert all(k["kp_id"] != "kp2" for k in keypoints)


def test_invalid_bloom_coerced_to_recall(monkeypatch):
    """Live: bloom_level outside the valid set is coerced to 'recall'."""
    live = {"concepts": [{"slug": "tool_use", "name": "Tool Use"}],
            "keypoints": [{"kp_id": "kp1", "concept_slug": "tool_use", "bloom_level": "MEMORIZE"}]}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    _, keypoints = extract.extract_concepts(_input(), candidate=CANDIDATE, session_id=None, conn=None)
    assert keypoints[0]["bloom_level"] == "recall"


def test_int_kp_id_coerced_not_dropped(monkeypatch):
    """Live LLMs often return kp_id as an INT; it must be coerced to str and KEPT, not discarded.
    The old isinstance(kp_id, str) check dropped it -> candidate fallback -> zero/ wrong keypoints,
    so live concepts had no real objectives. Twin of the D1 chunk-id coercion bug."""
    live = {"concepts": [{"slug": "tool_use", "name": "Tool Use"}],
            "keypoints": [{"kp_id": 1, "concept_slug": "tool_use",
                           "objective": "Understand what a tool call is.", "bloom_level": "recall"}]}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: live)
    _, keypoints = extract.extract_concepts(_input(), candidate=CANDIDATE, session_id=None, conn=None)
    assert len(keypoints) == 1, "int kp_id keypoint was dropped (regression)"
    assert keypoints[0]["kp_id"] == "1", "kp_id must be coerced to str"
    assert keypoints[0]["objective"].startswith("Understand"), "the live LLM objective must survive"
