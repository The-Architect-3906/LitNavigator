import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import extract


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
