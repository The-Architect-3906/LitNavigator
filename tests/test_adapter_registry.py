from litnav.discover.adapters import registry


def test_available_adapters_has_at_least_four():
    ads = registry.available_adapters()
    assert len(ads) >= 4


def test_descriptor_has_required_fields():
    for ad in registry.available_adapters():
        assert ad.id and isinstance(ad.id, str)
        assert ad.name and isinstance(ad.name, str)
        assert ad.description and isinstance(ad.description, str)
        assert isinstance(ad.default_on, bool)
        assert isinstance(ad.intent_affinity, list)
        assert callable(ad.search)


def test_resolve_none_returns_default_on():
    result = registry.resolve(None)
    default_ids = {ad.id for ad in registry.available_adapters() if ad.default_on}
    result_ids = {ad.id for ad in result}
    assert result_ids == default_ids


def test_resolve_empty_returns_default_on():
    result = registry.resolve([])
    default_ids = {ad.id for ad in registry.available_adapters() if ad.default_on}
    result_ids = {ad.id for ad in result}
    assert result_ids == default_ids


def test_resolve_specific_id():
    result = registry.resolve(["arxiv"])
    assert len(result) == 1
    assert result[0].id == "arxiv"


def test_resolve_unknown_id_silently_dropped():
    result = registry.resolve(["arxiv", "nonexistent_id_xyz"])
    assert len(result) == 1
    assert result[0].id == "arxiv"


def test_resolve_multiple_ids():
    result = registry.resolve(["openalex", "wikipedia"])
    result_ids = {ad.id for ad in result}
    assert result_ids == {"openalex", "wikipedia"}


from litnav.discover.contract import DiscoverInput


def test_discover_input_has_selected_adapters_field():
    di = DiscoverInput(goal_text="test")
    assert di.selected_adapters is None   # default

    di2 = DiscoverInput(goal_text="test", selected_adapters=["arxiv"])
    assert di2.selected_adapters == ["arxiv"]
