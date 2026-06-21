"""Typed contract for make-artifact (spec §6.4)."""
from __future__ import annotations
from dataclasses import dataclass, field

FORMATS = {"mindmap", "notes", "slides", "worked_example", "combination"}


@dataclass
class ArtifactInput:
    concept_ids: list[int]
    scenario: dict                 # {goal_type, user_request, content_kind}
    format: str | None = None      # optional override; else selected


@dataclass
class ArtifactResult:
    artifact_path: str
    format: str
    citations: list[str] = field(default_factory=list)
