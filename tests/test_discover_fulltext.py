from litnav.discover.contract import Source
from litnav.discover import fulltext

def test_fulltext_non_arxiv_uses_abstract():
    s = Source("web", "w", "u", "T", 0.5, abstract="just an abstract")
    assert fulltext.fetch_fulltext(s) == ["just an abstract"]

def test_fulltext_empty_when_nothing():
    s = Source("web", "w", "u", "T", 0.5, abstract="")
    assert fulltext.fetch_fulltext(s) == []

def test_attach_fulltext_only_top_k(monkeypatch):
    srcs = [Source("web", str(i), "u", f"T{i}", 0.5, abstract=f"abs{i}") for i in range(5)]
    fulltext.attach_fulltext(srcs, top_k=2)
    assert srcs[0].chunks == ["abs0"] and srcs[1].chunks == ["abs1"]
    assert srcs[2].chunks == [] and srcs[3].chunks == []   # beyond top_k untouched
