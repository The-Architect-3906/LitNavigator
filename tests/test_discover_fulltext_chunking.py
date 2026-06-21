from litnav.discover.contract import Source
from litnav.discover import fulltext


def _para(n):  # ~ n words
    return " ".join(["word"] * n)


def test_long_abstract_is_subchunked():
    long_abs = ". ".join([f"Sentence number {i} about the topic with enough words to matter" for i in range(40)]) + "."
    s = Source("web", "x", "u", "T", abstract=long_abs)
    chunks = fulltext.fetch_fulltext(s)
    assert len(chunks) >= 2, "long abstract must be split into multiple chunks"
    assert all(c.strip() for c in chunks)
    assert sum(len(c) for c in chunks) >= len(long_abs) * 0.8   # no major text loss
    assert len(chunks) <= 6                                      # capped


def test_short_abstract_single_chunk():
    s = Source("web", "x", "u", "T", abstract="A short abstract.")
    assert fulltext.fetch_fulltext(s) == ["A short abstract."]


def test_empty_abstract():
    s = Source("web", "x", "u", "T", abstract="")
    assert fulltext.fetch_fulltext(s) == []
