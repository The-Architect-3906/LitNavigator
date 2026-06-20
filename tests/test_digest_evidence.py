import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline


CANDIDATE = {
    "concepts": [{"slug": "a", "name": "A", "domain": "d", "frontier_flag": None}],
    "keypoints": [{"kp_id": "kp_a", "concept_slug": "a", "name": "k", "objective": "o",
                   "evidence_chunk_id": "c0", "bloom_level": "recall"}],
    "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {},
}


def test_digest_inserts_paper_chunks_so_evidence_resolves(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    di = DigestInput("d", [SourceDoc("arxiv", "2210.00001", "T", "http://x", ["chunk zero text", "chunk one text"])], [])
    pipeline.digest(di, conn=c, candidate=CANDIDATE, session_id="s")
    row = c.execute("SELECT source_type, url FROM papers WHERE arxiv_id='2210.00001'").fetchone()
    assert row == ("arxiv", "http://x")
    assert repo.get_chunk_text(c, "c0") == "chunk zero text"
    assert repo.get_chunk_text(c, "c1") == "chunk one text"
