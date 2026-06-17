import json
import sqlite3
from pathlib import Path

from litnav.ingest.pdf_extract import extract_paper_chunks
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

CORPUS = "data/seed/agents_corpus.json"


def test_extract_real_text_from_react_pdf():
    """Live extraction from the smallest PDF yields real, on-topic paper text (offline)."""
    chunks = extract_paper_chunks("2210.03629")  # ReAct
    assert chunks, "extraction produced chunks"
    text = " ".join(chunks).lower()
    assert len(text) > 300
    assert "react" in text or ("reason" in text and "act" in text)


def test_corpus_fixture_is_real_and_well_formed():
    data = json.loads(Path(CORPUS).read_text(encoding="utf-8"))
    assert len(data["papers"]) == 8
    concept_ids = {c["id"] for c in data["concepts"]}
    # every chunk is tagged to a real concept and has substantial real text
    for ch in data["chunks"]:
        assert ch["concept_id"] in concept_ids
        assert len(ch["text"]) > 80
    # every curated concept has at least one real chunk
    tagged = {ch["concept_id"] for ch in data["chunks"]}
    assert concept_ids <= tagged
    # the file is ASCII-safe (json escapes non-ASCII)
    assert all(ord(c) < 128 for c in Path(CORPUS).read_text(encoding="utf-8"))


def test_corpus_regeneration_is_idempotent():
    """Re-running extraction must reproduce the committed fixture byte-for-content.
    Guards against silent drift; fails loudly if the pinned pypdf version changes."""
    from litnav.ingest.pdf_extract import build_corpus
    committed = json.loads(Path(CORPUS).read_text(encoding="utf-8"))
    assert build_corpus() == committed, (
        "agents_corpus.json drifted from a fresh extraction — check the pinned pypdf version"
    )


def test_corpus_seeds_into_db_with_real_chunks():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, CORPUS)
    n_chunks = conn.execute("SELECT COUNT(*) FROM paper_chunks").fetchone()[0]
    assert n_chunks >= 24
    react = repo.get_concept_by_slug(conn, "react")
    react_chunks = conn.execute(
        "SELECT text FROM paper_chunks WHERE concept_id=?", (react["id"],)
    ).fetchall()
    assert react_chunks, "react concept has ingested chunks"
    assert any("act" in r[0].lower() for r in react_chunks)
