"""Typed contract for find-sources (DISCOVER)."""
from __future__ import annotations
from dataclasses import dataclass, field

INTENTS = {"crash-course", "systematic", "applied", "reference", "cutting-edge"}


@dataclass
class DiscoverInput:
    goal_text: str
    intent: str | None = None
    budget: int | None = None
    k: int = 6
    selected_adapters: list[str] | None = None


@dataclass
class Source:
    source_type: str
    source_id: str
    url: str | None
    title: str
    authority_score: float = 0.0
    why: str = ""
    abstract: str = ""
    arxiv_id: str | None = None
    chunks: list[str] = field(default_factory=list)


@dataclass
class DiscoverResult:
    sources: list[Source]
    intent_used: str
    cache_hit: bool = False
