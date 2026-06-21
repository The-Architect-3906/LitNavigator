import sqlite3
from litnav.storage.schema import init_db
from litnav.discover.contract import Source
from litnav.discover import rank

def _src(title, auth, abstract=""):
    return Source(source_type="web", source_id=title, url="u", title=title,
                  authority_score=auth, abstract=abstract)

def test_dedup_by_normalized_title():
    a = _src("ReAct: Reasoning and Acting", 0.9)
    b = _src("react reasoning and acting", 0.3)
    out = rank.dedup([a, b])
    assert len(out) == 1 and out[0].authority_score == 0.9

def test_rank_offline_is_authority_only(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src("low", 0.2, "agents"), _src("high", 0.8, "agents")]
    out = rank.rank_sources("agent reasoning", srcs, conn=c, session_id="s", k=2)
    assert [s.title for s in out] == ["high", "low"]

def test_rank_truncates_to_k(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    srcs = [_src(f"t{i}", i / 10) for i in range(8)]
    assert len(rank.rank_sources("q", srcs, conn=c, session_id="s", k=3)) == 3
