from litnav.discover.contract import Source
from litnav.discover.adapters._review import looks_like_review
from litnav.discover.adapters import openalex, semantic_scholar


def test_source_has_is_review_default_false():
    assert Source("web", "x", None, "T").is_review is False


def test_title_heuristic():
    assert looks_like_review("A Comprehensive Survey on Graph Neural Networks")
    assert looks_like_review("Deep Learning: A Review")
    assert looks_like_review("An Overview of Reinforcement Learning")
    assert not looks_like_review("Attention Is All You Need")


def test_openalex_sets_is_review_from_type():
    sample = {"results": [{"id": "https://openalex.org/W1", "title": "Neural Nets",
              "type": "review", "cited_by_count": 9, "primary_location": {}}]}
    s = openalex.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is True


def test_openalex_sets_is_review_from_title():
    sample = {"results": [{"id": "https://openalex.org/W2", "title": "A Survey of Agents",
              "type": "article", "cited_by_count": 9, "primary_location": {}}]}
    s = openalex.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is True


def test_s2_sets_is_review_from_publicationtypes():
    sample = {"data": [{"title": "Memory in LLMs", "publicationTypes": ["Review"],
              "citationCount": 3, "externalIds": {}, "openAccessPdf": None}]}
    s = semantic_scholar.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is True


def test_primary_paper_not_review():
    sample = {"results": [{"id": "https://openalex.org/W3", "title": "Attention Is All You Need",
              "type": "article", "cited_by_count": 99, "primary_location": {}}]}
    s = openalex.search("x", k=1, fetch=lambda u: sample)[0]
    assert s.is_review is False
