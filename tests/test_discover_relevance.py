import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import Source
from litnav.discover import relevance
from litnav.llm import router

def _src(t, a=""):
    return Source(source_type="web", source_id=t, url="u", title=t, abstract=a, authority_score=0.5)

def test_offline_passthrough(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("A"), _src("B")]
    assert relevance.relevance_gate("topic", srcs, conn=c, session_id="s") == srcs

def test_drops_irrelevant_keeps_rank_order(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": [0, 2]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("Raft paper"), _src("Megalopolis film"), _src("Paxos paper")]
    out = relevance.relevance_gate("raft consensus", srcs, conn=c, session_id="s", min_keep=1)
    assert [s.title for s in out] == ["Raft paper", "Paxos paper"]

def test_all_irrelevant_declines(monkeypatch):
    # A6: when the LLM marks NOTHING relevant (all score 0 = topic mismatch), decline honestly
    # rather than serving an off-topic source. (Was test_never_starves; the never-starve fallback
    # now only rescues at-least-weakly-on-topic sources, never pure mismatches.)
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": []})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("A"), _src("B"), _src("C")]
    out = relevance.relevance_gate("topic", srcs, conn=c, session_id="s", min_keep=2)
    assert out == []   # nothing relevant -> honest decline

def test_empty_input(monkeypatch):
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"relevant_indices": []})
    c = sqlite3.connect(":memory:"); init_db(c)
    assert relevance.relevance_gate("topic", [], conn=c, session_id="s") == []

def test_a14_scored_drops_same_family_different(monkeypatch):
    # A14: PBFT is "same family, different method" (score 1) for a Raft goal → dropped;
    # Raft (3) and a generic consensus paper (2) kept, best-scored first.
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"scores": [{"i": 0, "score": 3}, {"i": 1, "score": 1}, {"i": 2, "score": 2}]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("Raft paper"), _src("PBFT paper"), _src("Consensus survey")]
    out = relevance.relevance_gate("build a Raft consensus implementation", srcs, conn=c, session_id="s", min_keep=1)
    assert [s.title for s in out] == ["Raft paper", "Consensus survey"]   # PBFT (score 1) dropped

def test_a14_never_starves_when_all_low(monkeypatch):
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"scores": [{"i": 0, "score": 1}, {"i": 1, "score": 0}]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("best-of-bad"), _src("worse")]
    out = relevance.relevance_gate("x", srcs, conn=c, session_id="s", min_keep=1)
    assert [s.title for s in out] == ["best-of-bad"]   # highest score kept, never empty


def test_a6_declines_when_all_off_domain(monkeypatch):
    # A6: every candidate is topic-MISMATCHED (score 0 = different domain), even if high-authority.
    # The gate must DECLINE (return empty) rather than fall back to teaching an off-topic paper —
    # this is the "ReAct → psychological-reactance" bug. Empty → caller declines honestly.
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"scores": [{"i": 0, "score": 0}, {"i": 1, "score": 0}]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("Psychological Reactance in advertising", a="reactance theory"),
            _src("React.js component lifecycle", a="frontend framework")]
    out = relevance.relevance_gate("I want to understand ReAct", srcs,
                                   conn=c, session_id="s", min_keep=2)
    assert out == []   # nothing clears the topic-match bar → honest decline


def test_a6_keeps_on_domain_even_with_off_domain_present(monkeypatch):
    # When at least one source is on-domain (score >= 2), keep it and drop the off-domain noise.
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"scores": [{"i": 0, "score": 0}, {"i": 1, "score": 3}]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("Psychological Reactance"), _src("ReAct: Synergizing Reasoning and Acting in LLMs")]
    out = relevance.relevance_gate("I want to understand ReAct", srcs,
                                   conn=c, session_id="s", min_keep=2)
    assert [s.title for s in out] == ["ReAct: Synergizing Reasoning and Acting in LLMs"]


def test_a6_same_family_still_starves_to_keep(monkeypatch):
    # Regression: a score-1 "same family, different method" source is weak but NOT off-domain,
    # so the never-starve fallback still keeps it (digest gets something to chew on).
    monkeypatch.setattr(router, "complete_json",
                        lambda *a, **k: {"scores": [{"i": 0, "score": 1}]})
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("PBFT paper")]
    out = relevance.relevance_gate("build a Raft implementation", srcs,
                                   conn=c, session_id="s", min_keep=1)
    assert [s.title for s in out] == ["PBFT paper"]
