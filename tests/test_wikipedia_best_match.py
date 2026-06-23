"""Wikipedia keyword search floats junk on tail words (e.g. 'agent memory across steps' →
'The 39 Steps (1935 film)'). The adapter should re-rank the candidate hits by topical match to the
query and drop disambiguation junk, choosing the best article(s) — not trust Wikipedia's own order.
"""
from litnav.discover.adapters import wikipedia


def _fake(query_results, summaries):
    """Build a fetch() stub: search returns query_results; summary returns per-title summaries."""
    def fetch(url):
        if "list=search" in url:
            return {"query": {"search": query_results}}
        # summary endpoint: find which title is in the url
        for title, summ in summaries.items():
            if title.replace(" ", "_").replace(" ", "%20") in url or title.replace(" ", "%20") in url:
                return summ
        return {"title": "?", "extract": ""}
    return fetch


def test_picks_topical_article_over_tail_word_junk():
    results = [
        {"title": "The 39 Steps (1935 film)", "snippet": "a 1935 British thriller film"},
        {"title": "AI agent", "snippet": "an agent that uses memory to act over multiple steps"},
        {"title": "Reinforcement learning", "snippet": "agents learn from reward"},
    ]
    summaries = {t["title"]: {"title": t["title"], "extract": t["snippet"],
                             "content_urls": {"desktop": {"page": "u"}}} for t in results}
    out = wikipedia.search("agent memory across steps", k=1, fetch=_fake(results, summaries))
    assert out, "expected at least one hit"
    assert "film" not in out[0].title.lower()           # the junk film was dropped/down-ranked
    assert out[0].title == "AI agent"                    # the topical article was chosen


def test_falls_back_to_search_order_when_no_signal():
    results = [{"title": "Alpha", "snippet": "x"}, {"title": "Beta", "snippet": "y"}]
    summaries = {t["title"]: {"title": t["title"], "extract": "x",
                             "content_urls": {"desktop": {"page": "u"}}} for t in results}
    out = wikipedia.search("zzzz", k=2, fetch=_fake(results, summaries))
    assert {s.title for s in out} == {"Alpha", "Beta"}   # no topical signal → keep candidates
