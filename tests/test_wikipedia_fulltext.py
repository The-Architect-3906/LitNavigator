from litnav.discover.adapters import wikipedia
from litnav.discover.contract import Source
from litnav.discover import fulltext

_EXTRACT = {"query": {"pages": {"123": {"extract": "Graph neural networks are models. " * 400}}}}


def test_fetch_article_parses_extracts():
    art = wikipedia.fetch_article("Graph neural network", fetch=lambda u: _EXTRACT)
    assert len(art) > 1000          # full body, not the 103-char summary


def test_fetch_article_empty_on_failure():
    def boom(u):
        raise OSError("network")
    assert wikipedia.fetch_article("X", fetch=boom) == ""


def test_fulltext_uses_full_article_for_wikipedia(monkeypatch):
    monkeypatch.setattr(wikipedia, "fetch_article", lambda title, **k: "Body sentence. " * 300)
    s = Source("wikipedia", "Graph_neural_network", None, "Graph neural network",
               abstract="one sentence.")
    chunks = fulltext.fetch_fulltext(s)
    assert sum(len(c) for c in chunks) > 500   # far more than the 1-sentence abstract


def test_fulltext_falls_back_to_abstract_when_article_empty(monkeypatch):
    monkeypatch.setattr(wikipedia, "fetch_article", lambda title, **k: "")
    s = Source("wikipedia", "X", None, "X", abstract="a short abstract sentence.")
    chunks = fulltext.fetch_fulltext(s)
    assert chunks and "short abstract" in " ".join(chunks)
