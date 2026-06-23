"""Tests for Stack Exchange adapter. No network calls — inject fake fetch."""
import math
import urllib.parse

from litnav.discover.adapters import stack_exchange, registry

# ── Sample SE API v2.3 response ───────────────────────────────────────────────

SE_CANNED = {
    "items": [
        {
            "question_id": 12345678,
            "title": "How to implement Raft consensus algorithm in Python?",
            "body": "<p>I want to implement the Raft consensus algorithm. "
                    "Where do I start? What are the key components?</p>"
                    "<p>I've read the original paper but need practical guidance.</p>",
            "link": "https://stackoverflow.com/questions/12345678/how-to-implement-raft",
            "score": 42,
            "is_answered": True,
        },
        {
            "question_id": 87654321,
            "title": "Raft leader election — when does a candidate win?",
            "body": "<p>In Raft, a candidate wins an election when it receives "
                    "<strong>majority</strong> votes from the cluster.</p>",
            "link": "https://stackoverflow.com/questions/87654321/raft-leader-election",
            "score": 0,
            "is_answered": False,
        },
        {
            "question_id": 11111111,
            "title": "Log replication in Raft — commit index explained",
            "body": "<p>The <em>commit index</em> advances once a majority of followers "
                    "have appended the entry.</p>",
            "link": "https://stackoverflow.com/questions/11111111/raft-commit-index",
            "score": 1000,
            "is_answered": True,
        },
    ],
    "has_more": False,
    "quota_max": 300,
    "quota_remaining": 298,
}


# ── Parsing tests ─────────────────────────────────────────────────────────────

def test_se_parse_results():
    sources = stack_exchange.search("raft consensus implementation", k=10, fetch=lambda url: SE_CANNED)
    assert len(sources) == 3


def test_se_first_source_fields():
    sources = stack_exchange.search("raft consensus", k=10, fetch=lambda url: SE_CANNED)
    s0 = sources[0]
    assert s0.source_type == "stackoverflow"
    assert s0.source_id == "12345678"
    assert s0.url == "https://stackoverflow.com/questions/12345678/how-to-implement-raft"
    assert "Raft consensus" in s0.title
    assert s0.arxiv_id is None


def test_se_html_stripped_from_abstract():
    sources = stack_exchange.search("raft", k=10, fetch=lambda url: SE_CANNED)
    s0 = sources[0]
    # HTML tags must not appear in abstract
    assert "<p>" not in s0.abstract
    assert "<strong>" not in s0.abstract
    assert "<em>" not in s0.abstract
    # but text content should be present
    assert "Raft" in s0.abstract


def test_se_abstract_truncated_at_400_chars():
    long_body = "<p>" + "x" * 1000 + "</p>"
    canned = {"items": [{"question_id": 1, "title": "T", "body": long_body,
                          "link": "https://stackoverflow.com/q/1", "score": 5}]}
    s = stack_exchange.search("q", k=1, fetch=lambda url: canned)[0]
    assert len(s.abstract) <= 400


def test_se_authority_zero_score():
    sources = stack_exchange.search("raft", k=10, fetch=lambda url: SE_CANNED)
    s1 = sources[1]  # score=0
    assert s1.authority_score == 0.0


def test_se_authority_positive_score():
    sources = stack_exchange.search("raft", k=10, fetch=lambda url: SE_CANNED)
    s0 = sources[0]  # score=42
    assert 0.0 < s0.authority_score <= 1.0
    # verify formula: min(1.0, log(43)/log(1000))
    expected = round(min(1.0, math.log(43) / math.log(1000)), 4)
    assert s0.authority_score == expected


def test_se_authority_saturates_at_high_score():
    sources = stack_exchange.search("raft", k=10, fetch=lambda url: SE_CANNED)
    s2 = sources[2]  # score=1000 → should saturate at 1.0
    assert s2.authority_score == 1.0


def test_se_respects_k_limit():
    sources = stack_exchange.search("raft", k=2, fetch=lambda url: SE_CANNED)
    assert len(sources) == 2


def test_se_url_has_correct_params():
    captured = {}

    def fake(url):
        captured["url"] = url
        return {"items": []}

    stack_exchange.search("raft consensus implementation", k=5, fetch=fake)
    u = captured["url"]
    assert "api.stackexchange.com" in u
    assert "stackoverflow" in u
    assert "sort=relevance" in u
    assert "pagesize=5" in u
    assert urllib.parse.quote("raft consensus implementation") in u or "raft" in u


def test_se_non_fatal_on_network_error():
    def bad_fetch(url):
        raise OSError("network down")

    result = stack_exchange.search("raft", k=5, fetch=bad_fetch)
    assert result == []


def test_se_empty_items():
    sources = stack_exchange.search("raft", k=5, fetch=lambda url: {"items": []})
    assert sources == []


def test_se_missing_items_key():
    sources = stack_exchange.search("raft", k=5, fetch=lambda url: {})
    assert sources == []


# ── Registry tests ────────────────────────────────────────────────────────────

def test_registry_has_stack_exchange():
    ids = {ad.id for ad in registry.available_adapters()}
    assert "stack_exchange" in ids


def test_stack_exchange_not_default_on():
    ad = next(ad for ad in registry.available_adapters() if ad.id == "stack_exchange")
    assert ad.default_on is False


def test_stack_exchange_intent_affinity():
    ad = next(ad for ad in registry.available_adapters() if ad.id == "stack_exchange")
    assert "applied" in ad.intent_affinity


def test_stack_exchange_not_in_default_resolve():
    result = registry.resolve(None)
    result_ids = {ad.id for ad in result}
    assert "stack_exchange" not in result_ids


def test_stack_exchange_in_resolve_when_selected():
    result = registry.resolve(["stack_exchange"])
    assert len(result) == 1
    assert result[0].id == "stack_exchange"
    assert callable(result[0].search)
