import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo, openworld_repo
from litnav.digest.contract import DigestInput, SourceDoc, slice_key
from litnav.digest import pipeline


CANDIDATE = {
    "concepts": [
        {"slug": "tool_use", "name": "Tool Use", "domain": "llm-agents", "frontier_flag": None},
        {"slug": "reason_act", "name": "Reasoning + Acting", "domain": "llm-agents", "frontier_flag": None},
    ],
    "keypoints": [
        {"kp_id": "kp_tool_1", "concept_slug": "tool_use", "name": "What a tool call is",
         "objective": "define", "evidence_chunk_id": "c0", "bloom_level": "recall"},
    ],
    "prereq_edges": [
        {"prereq_slug": "tool_use", "target_slug": "reason_act",
         "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False},
    ],
    "similarity_edges": [],
    "quiz_seeds": [
        {"concept_slug": "tool_use", "question": "What is a tool call?", "answer_key": "...",
         "keypoint_id": "kp_tool_1", "bloom_level": "recall"},
    ],
    "judge_labels": {"tool_use->reason_act": True},
}


def _input():
    return DigestInput("llm-agents",
                       [SourceDoc("arxiv", "2302.04761", "Toolformer", None, ["c0 text", "c1 text"])],
                       target_slugs=[])


def _conn():
    c = sqlite3.connect(":memory:"); init_db(c); return c


def test_digest_writes_graph_with_digested_source(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _conn()
    res = pipeline.digest(_input(), conn=c, candidate=CANDIDATE, session_id="s")
    rows = c.execute("SELECT slug, source, domain FROM concepts ORDER BY slug").fetchall()
    assert ("tool_use", "digested", "llm-agents") in rows
    digested_edges = repo.get_concept_edges(c, source="digested")
    pe = [e for e in digested_edges if e["edge_type"] == "prerequisite"][0]
    assert pe["confidence"] == 0.75
    cid = c.execute("SELECT id FROM concepts WHERE slug='tool_use'").fetchone()[0]
    assert repo.get_keypoints(c, cid)
    assert repo.get_quiz_item(c, cid) is not None
    assert res.edge_accuracy == 1.0 and res.cache_hit is False


def test_second_identical_request_is_cache_hit(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _conn()
    pipeline.digest(_input(), conn=c, candidate=CANDIDATE, session_id="s")
    key = slice_key("llm-agents", ["2302.04761"], [])
    assert openworld_repo.cache_get(c, key)["status"] == "cached"
    res2 = pipeline.digest(_input(), conn=c, candidate=CANDIDATE, session_id="s")
    assert res2.cache_hit is True


def test_digest_is_zero_cost_offline(monkeypatch):
    from litnav.storage import cost_repo
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = _conn()
    pipeline.digest(_input(), conn=c, candidate=CANDIDATE, session_id="s")
    assert cost_repo.session_spend(c, "s")["usd"] == 0.0
