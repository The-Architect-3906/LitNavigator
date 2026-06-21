"""OW-5.1 regression: the digest→teach→artifact PERSISTENCE chain on real-shaped data.

These guard the bugs a fresh-topic live run exposed (and that the old gates missed because
they asserted on in-memory returns / hand-seeded clean fixtures):
  - create_concept silently dropped concepts whose LLM frontier_flag violated the CHECK;
  - keypoint evidence_chunk_id ('1','2'...) never matched the 'cN' chunk ids -> no evidence;
  - make_artifact read only paper_chunks.concept_id (NULL for digested data) -> empty artifacts.
"""
import os
import sqlite3
import tempfile

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact

# A digest candidate as an LLM would realistically produce it: an out-of-vocab frontier_flag
# and a keypoint evidence_chunk_id that does NOT match the 'cN' chunk ids.
CAND = {
    "concepts": [
        {"slug": "alpha", "name": "Alpha", "frontier_flag": "established"},  # invalid flag
        {"slug": "beta", "name": "Beta", "frontier_flag": "consensus"},       # valid flag
    ],
    "keypoints": [
        {"kp_id": "k1", "concept_slug": "alpha", "name": "Alpha kp",
         "objective": "alpha core objective", "evidence_chunk_id": "1", "bloom_level": "recall"},
        {"kp_id": "k2", "concept_slug": "beta", "name": "Beta kp",
         "objective": "beta core objective", "evidence_chunk_id": "c0", "bloom_level": "recall"},
    ],
    "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {},
}


def _digest_into(c):
    di = DigestInput("dom",
                     [SourceDoc("web", "src1", "Src", "http://x", ["chunk zero text", "chunk one text"])],
                     target_slugs=[])
    return pipeline.digest(di, conn=c, candidate=CAND, session_id="s")


def test_create_concept_coerces_invalid_frontier_flag():
    c = sqlite3.connect(":memory:"); init_db(c)
    repo.create_concept(c, 1, "x", "X", "established", source="digested")  # not in CHECK set
    row = c.execute("SELECT slug, frontier_flag FROM concepts WHERE id=1").fetchone()
    assert row == ("x", None)   # row PERSISTED, flag coerced to NULL (not silently dropped)


def test_digest_persists_concepts_and_keypoint_evidence_resolves(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    _digest_into(c)
    # Both concepts persisted — including the one with the bad frontier_flag.
    assert c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2
    # Every keypoint's evidence_chunk_id resolves to a real chunk.
    valid = {r[0] for r in c.execute("SELECT id FROM paper_chunks").fetchall()}
    ecids = [r[0] for r in c.execute("SELECT evidence_chunk_id FROM keypoints").fetchall()]
    assert ecids and all(e in valid for e in ecids), f"unresolved keypoint evidence: {ecids} vs {valid}"


CAND_NO_KP = {
    "concepts": [{"slug": "gamma", "name": "Gamma", "frontier_flag": None},
                 {"slug": "delta", "name": "Delta", "frontier_flag": None}],
    "keypoints": [],
    "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {},
}


def test_make_artifact_source_pool_fallback_when_no_keypoints(monkeypatch):
    # Extraction is non-deterministic and sometimes yields 0 keypoints; the artifact must still
    # be GROUNDED in the source chunks the concepts came from (not bluff with no citations).
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    di = DigestInput("dom",
                     [SourceDoc("web", "src1", "Src", "http://x",
                                ["alpha source sentence one", "beta source sentence two"])],
                     target_slugs=[])
    pipeline.digest(di, conn=c, candidate=CAND_NO_KP, session_id="s")
    assert c.execute("SELECT COUNT(*) FROM keypoints").fetchone()[0] == 0
    ids = [r[0] for r in c.execute("SELECT id FROM concepts ORDER BY id").fetchall()]
    res = make_artifact(ArtifactInput(ids, {}, format="notes"),
                        conn=c, session_id="s", out_dir=tempfile.mkdtemp())
    assert res.citations, "no source-pool fallback citations"
    valid = {r[0] for r in c.execute("SELECT id FROM paper_chunks").fetchall()}
    assert all(x in valid for x in res.citations)


def test_make_artifact_from_digested_graph_nonempty_with_resolving_citations(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    _digest_into(c)
    ids = [r[0] for r in c.execute("SELECT id FROM concepts ORDER BY id").fetchall()]
    assert ids, "no concepts persisted"

    # mindmap (survey/structure) renders the digested concepts
    res = make_artifact(ArtifactInput(ids, {"goal_type": "survey", "content_kind": "structure", "user_request": ""}),
                        conn=c, session_id="s", out_dir=tempfile.mkdtemp())
    body = open(res.artifact_path, encoding="utf-8").read()
    assert "Alpha" in body and "Beta" in body

    # notes must be NON-EMPTY, grounded in the keypoint objectives, with RESOLVING citations
    res2 = make_artifact(ArtifactInput(ids, {}, format="notes"),
                         conn=c, session_id="s", out_dir=tempfile.mkdtemp())
    nbody = open(res2.artifact_path, encoding="utf-8").read()
    assert "Alpha" in nbody and "Beta" in nbody
    assert res2.citations, "no citations produced from digested graph"
    valid = {r[0] for r in c.execute("SELECT id FROM paper_chunks").fetchall()}
    assert all(cit in valid for cit in res2.citations), "citations do not resolve to real chunks"
