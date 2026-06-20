"""Typed contract for the digest pipeline. Dataclasses for inputs/outputs; the graph rows
themselves stay plain dicts (they map straight to repo writers). slice_key() is the cache key."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# An edge whose computed confidence is below this is NOT trusted as a hard prerequisite:
# it is downgraded to 'similarity' and flagged in unverified_edges (lit-review risk A).
VERIFY_THRESHOLD = 0.60
# A prereq edge at/above this confidence on the goal slice is "high impact" -> gets the frontier verify pass.
HIGH_IMPACT_MIN_CONF = 0.60


@dataclass
class SourceDoc:
    source_type: str            # arxiv | wikipedia | youtube | pdf | web
    source_id: str
    title: str
    url: str | None
    chunks: list[str]           # already-chunked text


@dataclass
class DigestInput:
    domain_key: str
    sources: list[SourceDoc]
    target_slugs: list[str] = field(default_factory=list)  # [] => digest all extracted concepts


@dataclass
class DigestResult:
    domain_key: str
    concepts: list[dict]
    edges: list[dict]
    keypoints: list[dict]
    quiz_seeds: list[dict]
    unverified_edges: list[dict]
    edge_accuracy: float
    cache_hit: bool = False


def slice_key(domain_key: str, source_ids: list[str], target_slugs: list[str]) -> str:
    """Deterministic, order-independent cache key for a digest request."""
    payload = json.dumps(
        {"d": domain_key, "s": sorted(source_ids), "t": sorted(target_slugs)},
        sort_keys=True, ensure_ascii=True,
    )
    return "dg_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
