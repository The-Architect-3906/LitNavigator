from litnav.discover.contract import Source
from litnav.discover import rank

def _src(title, abstract=""):
    return Source("web", title, "u", title, 0.5, abstract=abstract)

def test_bm25_prefilter_ranks_overlap_first():
    srcs = [_src("unrelated cooking recipes", "pasta"),
            _src("agent reasoning and tools", "llm agents reason and act with tools"),
            _src("agent memory", "agents store memory")]
    out = rank.bm25_prefilter("llm agents reasoning tools", srcs, keep=2)
    assert len(out) == 2
    assert out[0].title == "agent reasoning and tools"      # highest term overlap first
    assert all(s.title != "unrelated cooking recipes" for s in out)  # no-overlap dropped

def test_bm25_prefilter_keep_bounds():
    srcs = [_src(f"agent topic {i}", "agents") for i in range(10)]
    assert len(rank.bm25_prefilter("agent", srcs, keep=4)) == 4

def test_bm25_prefilter_empty_query_keeps_input_order():
    srcs = [_src("a", "x"), _src("b", "y")]
    out = rank.bm25_prefilter("", srcs, keep=5)
    assert {s.title for s in out} == {"a", "b"}
