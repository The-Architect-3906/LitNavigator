from litnav.digest import refd


def test_refd_directional_asymmetry():
    concepts = [{"slug": "a", "name": "advanced topic"}, {"slug": "b", "name": "basic topic"}]
    by_chunk = {"c0": "basic topic explained", "c1": "advanced topic uses basic topic"}
    scores = refd.refd_scores(concepts, by_chunk)
    assert scores[("b", "a")] > 0      # prereq=b, target=a: a references b more than b references a
    assert scores[("a", "b")] <= 0


def test_refd_no_cooccurrence_is_zero():
    concepts = [{"slug": "a", "name": "alpha"}, {"slug": "b", "name": "beta"}]
    by_chunk = {"c0": "alpha only", "c1": "beta only"}
    scores = refd.refd_scores(concepts, by_chunk)
    assert scores[("a", "b")] == 0 and scores[("b", "a")] == 0
