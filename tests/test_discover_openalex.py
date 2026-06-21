from litnav.discover.adapters import openalex

CANNED = {"results": [
    {"id": "https://openalex.org/W1", "title": "ReAct: Synergizing Reasoning and Acting",
     "abstract_inverted_index": {"We": [0], "study": [1], "agents": [2]},
     "cited_by_count": 1200, "ids": {"arxiv": "2210.03629"},
     "primary_location": {"pdf_url": "http://arxiv.org/pdf/2210.03629", "landing_page_url": "http://x"},
     "open_access": {"oa_url": "http://arxiv.org/pdf/2210.03629"}},
    {"id": "https://openalex.org/W2", "title": "Some Web Page", "abstract_inverted_index": None,
     "cited_by_count": 0, "ids": {}, "primary_location": {"landing_page_url": "http://y"},
     "open_access": {"oa_url": None}},
]}


def test_parse_openalex_results():
    sources = openalex.search("react agents", k=10, fetch=lambda url: CANNED)
    assert len(sources) == 2
    s0 = sources[0]
    assert s0.title.startswith("ReAct") and s0.arxiv_id == "2210.03629"
    assert s0.abstract == "We study agents"
    assert 0.0 < s0.authority_score <= 1.0
    assert s0.url == "http://arxiv.org/pdf/2210.03629"
    assert s0.source_type == "arxiv"
    s1 = sources[1]
    assert s1.arxiv_id is None and s1.authority_score == 0.0 and s1.source_type == "web"


def test_query_is_url_encoded():
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"results": []}
    openalex.search("multi agent debate", k=5, fetch=fake)
    assert ("multi%20agent%20debate" in captured["url"]) or ("multi+agent+debate" in captured["url"])
    assert "per_page=5" in captured["url"]


def test_arxiv_id_extracted_from_abs_url():
    canned = {"results": [{"id": "https://openalex.org/W3", "title": "X",
              "abstract_inverted_index": None, "cited_by_count": 5,
              "ids": {"arxiv": "https://arxiv.org/abs/2305.14325"}, "primary_location": {}, "open_access": {}}]}
    s = openalex.search("q", fetch=lambda url: canned)[0]
    assert s.arxiv_id == "2305.14325"
