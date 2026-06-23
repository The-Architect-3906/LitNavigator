"""Tests for Semantic Scholar and arXiv adapters. No network calls — inject fake fetch."""
import urllib.parse
from litnav.discover.adapters import semantic_scholar, arxiv

# ── Semantic Scholar ──────────────────────────────────────────────────────────

S2_CANNED = {
    "data": [
        {
            "paperId": "abc123",
            "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
            "abstract": "We explore the use of LLMs to generate reasoning traces.",
            "tldr": {"model": "tldr@v2.0.0", "text": "A method combining reasoning and acting."},
            "citationCount": 2500,
            "externalIds": {"ArXiv": "2210.03629"},
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2210.03629", "status": "GREEN"},
            "year": 2022,
        },
        {
            "paperId": "def456",
            "title": "No Abstract Paper",
            "abstract": None,
            "tldr": {"model": "tldr@v2.0.0", "text": "Short summary only."},
            "citationCount": 50,
            "externalIds": {},
            "openAccessPdf": None,
            "year": 2023,
        },
    ],
    "total": 2,
    "offset": 0,
    "next": 2,
}


def test_s2_parse_results():
    sources = semantic_scholar.search("react agents", k=10, fetch=lambda url: S2_CANNED)
    assert len(sources) == 2

    s0 = sources[0]
    assert s0.title.startswith("ReAct")
    assert s0.source_type == "arxiv"
    assert s0.arxiv_id == "2210.03629"
    assert s0.source_id == "abc123"
    assert "LLMs" in s0.abstract
    assert s0.url == "https://arxiv.org/pdf/2210.03629"
    assert 0.0 < s0.authority_score <= 1.0

    s1 = sources[1]
    assert s1.source_type == "web"
    assert s1.arxiv_id is None
    # abstract falls back to tldr.text when abstract is None
    assert "Short summary only" in s1.abstract
    assert "semanticscholar.org" in s1.url


def test_s2_url_has_query_and_fields():
    captured = {}
    def fake(url):
        captured["url"] = url
        return {"data": []}
    semantic_scholar.search("multi agent debate", k=5, fetch=fake)
    u = captured["url"]
    assert "paper/search" in u
    assert "query=" in u
    assert "fields=" in u
    assert "limit=5" in u


def test_s2_authority_zero_citations():
    canned = {"data": [{"paperId": "z1", "title": "Zero Cites", "abstract": "x",
                         "tldr": None, "citationCount": 0, "externalIds": {},
                         "openAccessPdf": None, "year": 2024}]}
    s = semantic_scholar.search("q", k=1, fetch=lambda url: canned)[0]
    assert s.authority_score == 0.0


def test_s2_tldr_fallback_when_no_abstract():
    canned = {"data": [{"paperId": "z2", "title": "T", "abstract": "",
                         "tldr": {"text": "TLDR text here."}, "citationCount": 10,
                         "externalIds": {}, "openAccessPdf": None, "year": 2024}]}
    s = semantic_scholar.search("q", k=1, fetch=lambda url: canned)[0]
    assert s.abstract == "TLDR text here."


# ── arXiv ─────────────────────────────────────────────────────────────────────

ARXIV_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2210.03629v1</id>
    <title>ReAct: Synergizing Reasoning and Acting</title>
    <summary>We explore reasoning traces and acting in LLMs.</summary>
    <author><name>Shunyu Yao</name></author>
    <link href="http://arxiv.org/pdf/2210.03629v1" rel="related" type="application/pdf"/>
    <link href="http://arxiv.org/abs/2210.03629v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2305.14325v2</id>
    <title>Toolformer: Language Models Can Teach Themselves to Use Tools</title>
    <summary>We introduce Toolformer, a model trained to use APIs.</summary>
    <author><name>Timo Schick</name></author>
    <link href="http://arxiv.org/abs/2305.14325v2" rel="alternate" type="text/html"/>
  </entry>
</feed>"""


def test_arxiv_parse_results():
    sources = arxiv.search("react agents", k=5, fetch=lambda url: ARXIV_ATOM)
    assert len(sources) == 2

    s0 = sources[0]
    assert s0.title == "ReAct: Synergizing Reasoning and Acting"
    assert s0.source_type == "arxiv"
    assert s0.arxiv_id == "2210.03629"
    assert s0.source_id == "2210.03629"
    assert "reasoning traces" in s0.abstract
    assert s0.authority_score == 0.35
    assert s0.url is not None and "arxiv.org" in s0.url

    s1 = sources[1]
    assert s1.arxiv_id == "2305.14325"
    assert "Toolformer" in s1.title


def test_arxiv_url_has_search_query():
    captured = {}
    def fake(url):
        captured["url"] = url
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    arxiv.search("multi agent debate", k=3, fetch=fake)
    u = captured["url"]
    assert "export.arxiv.org" in u
    assert "max_results=3" in u
    assert "search_query=" in u


def test_arxiv_source_type_is_arxiv():
    sources = arxiv.search("q", k=5, fetch=lambda url: ARXIV_ATOM)
    assert all(s.source_type == "arxiv" for s in sources)
