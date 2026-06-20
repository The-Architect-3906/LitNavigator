import pytest
from litnav.llm import registry


def test_enabled_tiers_resolve_to_model_and_rate():
    cheap = registry.resolve_tier("cheap")
    assert cheap["model"] == "gpt-4o-mini"
    assert cheap["usd_per_1k"] > 0
    frontier = registry.resolve_tier("frontier")
    assert frontier["model"] == "gpt-4o"
    assert frontier["usd_per_1k"] > cheap["usd_per_1k"]   # frontier costs more


def test_unknown_tier_raises():
    with pytest.raises(ValueError):
        registry.resolve_tier("made_up")


def test_record_only_models_exist_but_are_not_callable():
    # Recorded needs are visible for governance but never resolvable as a callable tier.
    assert registry.RECORDED_NEEDS, "recorded needs list should not be empty (it documents asks)"
    for need in registry.RECORDED_NEEDS:
        assert "name" in need and "why" in need
        with pytest.raises(ValueError):
            registry.resolve_tier(need["name"])   # cannot be called silently


def test_is_enabled():
    assert registry.is_enabled("cheap") is True
    assert registry.is_enabled("frontier") is True
    assert registry.is_enabled("made_up") is False
