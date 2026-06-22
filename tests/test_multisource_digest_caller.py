"""Fix A.4: the cold-start caller must feed digest the top-3 full-text sources (backbone first),
not just the single top source. This pins the selection/ordering helper used by _build_open_world."""
from litnav.ui.interactive import _pick_digest_sources


class _S:
    def __init__(self, i, review=False, stype="web"):
        self.source_type = stype
        self.source_id = str(i)
        self.title = f"T{i}"
        self.url = None
        self.chunks = ["x" * 300]
        self.is_review = review


def test_top3_cap():
    assert len(_pick_digest_sources([_S(i) for i in range(5)])) == 3
    assert len(_pick_digest_sources([_S(0)])) == 1
    assert _pick_digest_sources([]) == []


def test_backbone_first():
    # a review/wikipedia source should be ordered first (the general-concepts backbone)
    primary = _S(1)
    review = _S(2, review=True)
    wiki = _S(3, stype="wikipedia")
    out = _pick_digest_sources([primary, review, wiki])
    assert out[0].is_review or out[0].source_type == "wikipedia"
