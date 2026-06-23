from litnav.discover.adapters import wikipedia

SEARCH = {"query": {"search": [{"title": "ReAct (machine learning)", "snippet": "a paradigm"},
                               {"title": "Software agent", "snippet": "an agent"}]}}
SUMMARY = {"ReAct (machine learning)": {"title": "ReAct (machine learning)",
            "extract": "ReAct is a prompting paradigm.", "content_urls": {"desktop": {"page": "http://w/ReAct"}}},
           "Software agent": {"title": "Software agent", "extract": "A software agent acts.",
            "content_urls": {"desktop": {"page": "http://w/Agent"}}}}


def test_parse_wikipedia():
    import urllib.parse as _u
    def fetch(url):
        if "list=search" in url:
            return SEARCH
        for title, summ in SUMMARY.items():
            if _u.quote(title.replace(" ", "_")) in url:
                return summ
        return {}
    sources = wikipedia.search("react agents", k=2, fetch=fetch)
    assert len(sources) == 2
    assert sources[0].source_type == "wikipedia"
    assert sources[0].title == "ReAct (machine learning)"
    assert "prompting paradigm" in sources[0].abstract
    assert sources[0].url == "http://w/ReAct"
    assert sources[0].authority_score == 0.5


def test_search_url_has_query_and_limit():
    captured = []
    def fetch(url):
        captured.append(url)
        return {"query": {"search": []}} if "list=search" in url else {}
    wikipedia.search("multi agent debate", k=4, fetch=fetch)
    # srsearch present; srlimit present (a candidate pool ≥ k is fetched, then re-ranked to top-k —
    # the exact pool size is an impl detail, so we don't pin it to k).
    assert any("srsearch=" in u and "srlimit=" in u for u in captured)
