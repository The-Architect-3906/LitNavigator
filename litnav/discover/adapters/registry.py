"""Selectable-adapter registry for DISCOVER.

Each AdapterDescriptor exposes UI-facing metadata (id, name, description,
default_on, intent_affinity) plus a `search` callable so callers never need
to import adapter modules directly.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from litnav.discover.contract import Source
from litnav.discover.adapters import openalex, wikipedia, semantic_scholar, arxiv


@dataclass
class AdapterDescriptor:
    id: str
    name: str
    description: str
    default_on: bool
    intent_affinity: list[str]
    search: Callable[[str, int], list[Source]]


_REGISTRY: list[AdapterDescriptor] = [
    AdapterDescriptor(
        id="openalex",
        name="OpenAlex",
        description="200M+ scholarly works; citation-based authority scoring.",
        default_on=True,
        intent_affinity=["crash-course", "systematic", "applied", "reference", "cutting-edge"],
        search=openalex.search,
    ),
    AdapterDescriptor(
        id="wikipedia",
        name="Wikipedia",
        description="Encyclopedic background; good for concept overviews.",
        default_on=True,
        intent_affinity=["crash-course", "reference"],
        search=wikipedia.search,
    ),
    AdapterDescriptor(
        id="semantic_scholar",
        name="Semantic Scholar",
        description="ML-ranked scholarly search with TLDRs; fixes tangential-paper problem.",
        default_on=True,
        intent_affinity=["crash-course", "systematic", "applied", "reference", "cutting-edge"],
        search=semantic_scholar.search,
    ),
    AdapterDescriptor(
        id="arxiv",
        name="arXiv Direct Search",
        description="Preprint relevance search; surfaces recent ML/CS papers before peer review.",
        default_on=True,
        intent_affinity=["cutting-edge", "systematic"],
        search=arxiv.search,
    ),
]


def available_adapters() -> list[AdapterDescriptor]:
    """Return all registered adapter descriptors."""
    return list(_REGISTRY)


def resolve(selected_ids: list[str] | None) -> list[AdapterDescriptor]:
    """Return adapters for the given id list, or all default_on if None/empty."""
    if not selected_ids:
        return [ad for ad in _REGISTRY if ad.default_on]
    id_set = set(selected_ids)
    return [ad for ad in _REGISTRY if ad.id in id_set]
