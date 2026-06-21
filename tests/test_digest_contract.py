from litnav.digest.contract import (SourceDoc, DigestInput, DigestResult,
                                     slice_key, VERIFY_THRESHOLD, HIGH_IMPACT_MIN_CONF)


def test_constants_are_sane():
    assert 0.0 < VERIFY_THRESHOLD < 1.0
    assert 0.0 < HIGH_IMPACT_MIN_CONF < 1.0


def test_slice_key_is_deterministic_and_order_independent():
    k1 = slice_key("llm-agents", ["s2", "s1"], ["b", "a"])
    k2 = slice_key("llm-agents", ["s1", "s2"], ["a", "b"])
    assert k1 == k2  # source/target order must not change the key


def test_slice_key_changes_with_domain():
    assert slice_key("a", ["s1"], []) != slice_key("b", ["s1"], [])


def test_digest_input_holds_sources():
    di = DigestInput(domain_key="llm-agents",
                     sources=[SourceDoc("arxiv", "2302.04761", "Toolformer", None, ["c0", "c1"])],
                     target_slugs=["tool_use"])
    assert di.sources[0].chunks == ["c0", "c1"]


def test_digest_result_defaults():
    r = DigestResult(domain_key="d", concepts=[], edges=[], keypoints=[],
                     quiz_seeds=[], unverified_edges=[], edge_accuracy=1.0)
    assert r.cache_hit is False
