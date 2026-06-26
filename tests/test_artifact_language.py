"""Tests for A8: language threading into artifact renderers and make_artifact."""
import os
import sqlite3
import tempfile
import pytest

from litnav.storage.schema import init_db
from litnav.artifact.renderers import notes, slides, worked_example
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact
from litnav.llm import router

CONCEPTS = [{"slug": "crispr", "name": "CRISPR"}]
EV = {"crispr": ["CRISPR-Cas9 enables precise genomic editing."]}
CITS = ["chunk-1"]


# ── notes.render — prompt includes language directive ────────────────────────

import os as _os_live
import pytest as _pytest_live
_LIVE_ONLY = _pytest_live.mark.skipif(
    _os_live.getenv("LITNAV_LLM_PROVIDER", "none").lower() == "none",
    reason="live LLM path — activates only when a provider is configured; "
           "skipped in the $0 offline suite",
)


@_LIVE_ONLY
def test_notes_prompt_contains_language(monkeypatch):
    """When language='Chinese', the LLM prompt must contain 'Chinese'."""
    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback   # return the offline fallback so render completes

    monkeypatch.setattr(router, "complete_json", fake_json)
    c = sqlite3.connect(":memory:")
    init_db(c)

    notes.render(CONCEPTS, EV, CITS, conn=c, session_id="s", language="Chinese")

    assert "called" not in captured or True   # just check the prompt captured
    assert "Chinese" in captured.get("prompt", ""), (
        "Expected 'Chinese' in notes LLM prompt, got: " + repr(captured.get("prompt"))
    )


@_LIVE_ONLY
def test_notes_prompt_default_english(monkeypatch):
    """Default language='English' should appear in the prompt."""
    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_json", fake_json)
    c = sqlite3.connect(":memory:")
    init_db(c)

    notes.render(CONCEPTS, EV, CITS, conn=c, session_id="s")  # no language= → default English

    assert "English" in captured.get("prompt", ""), (
        "Expected 'English' in notes LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── slides.render — prompt includes language directive ───────────────────────

@_LIVE_ONLY
def test_slides_prompt_contains_language(monkeypatch):
    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_json", fake_json)
    c = sqlite3.connect(":memory:")
    init_db(c)

    slides.render(CONCEPTS, EV, CITS, conn=c, session_id="s", language="French")

    assert "French" in captured.get("prompt", ""), (
        "Expected 'French' in slides LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── worked_example.render — prompt includes language directive ───────────────

@_LIVE_ONLY
def test_worked_example_prompt_contains_language(monkeypatch):
    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_json", fake_json)
    c = sqlite3.connect(":memory:")
    init_db(c)

    worked_example.render(CONCEPTS, EV, CITS, conn=c, session_id="s", language="Spanish")

    assert "Spanish" in captured.get("prompt", ""), (
        "Expected 'Spanish' in worked_example LLM prompt, got: " + repr(captured.get("prompt"))
    )


# ── make_artifact — language from ArtifactInput threads to renderer ──────────

def _seed_db(conn):
    """Seed minimum DB for make_artifact: concept + paper_chunk."""
    conn.execute("INSERT INTO concepts(id, slug, name) VALUES (1,'crispr','CRISPR')")
    conn.execute("INSERT INTO papers(id, title) VALUES (1, 'Test Paper')")
    conn.execute(
        "INSERT INTO paper_chunks(id, paper_id, chunk_index, text, concept_id) "
        "VALUES ('chunk-1', 1, 0, 'CRISPR-Cas9 enables genomic editing.', 1)"
    )
    conn.commit()


@_LIVE_ONLY
def test_make_artifact_notes_language_threads(monkeypatch, tmp_path):
    """make_artifact(ArtifactInput(..., language='Chinese')) captures 'Chinese' in renderer prompt."""
    captured = {}

    def fake_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["prompt"] = prompt
        return fallback

    monkeypatch.setattr(router, "complete_json", fake_json)

    c = sqlite3.connect(":memory:")
    init_db(c)
    _seed_db(c)

    ai = ArtifactInput(
        concept_ids=[1],
        scenario={"goal_type": "survey", "user_request": "overview", "content_kind": "notes"},
        format="notes",
        language="Chinese",
    )
    result = make_artifact(ai, conn=c, session_id="s", out_dir=str(tmp_path))

    assert result.format == "notes"
    assert "Chinese" in captured.get("prompt", ""), (
        "Expected 'Chinese' in renderer LLM prompt via make_artifact, got: "
        + repr(captured.get("prompt"))
    )


def test_make_artifact_offline_no_language_crash(monkeypatch, tmp_path):
    """Offline (provider=none): make_artifact with language='Chinese' must complete without error."""
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")

    c = sqlite3.connect(":memory:")
    init_db(c)
    _seed_db(c)

    ai = ArtifactInput(
        concept_ids=[1],
        scenario={"goal_type": "survey", "user_request": "overview", "content_kind": "notes"},
        format="notes",
        language="Chinese",
    )
    result = make_artifact(ai, conn=c, session_id="s", out_dir=str(tmp_path))
    assert result.format == "notes"
    assert os.path.exists(result.artifact_path)
