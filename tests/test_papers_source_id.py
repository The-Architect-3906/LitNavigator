import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline

def test_create_paper_generic_source_id():
    c = sqlite3.connect(":memory:"); init_db(c)
    pid = repo.create_paper(c, source_id="Software_agent", title="Software agent",
                            source_type="wikipedia", url="http://w")
    row = c.execute("SELECT source_id, source_type, arxiv_id FROM papers WHERE id=?", (pid,)).fetchone()
    assert row[0] == "Software_agent" and row[1] == "wikipedia" and row[2] is None  # not in arxiv_id

def test_digest_stores_source_id_per_type(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    cand = {"concepts": [{"slug": "a", "name": "A", "domain": "d", "frontier_flag": None}],
            "keypoints": [], "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {}}
    di = DigestInput("d", [SourceDoc("wikipedia", "Software_agent", "Software agent", "http://w", ["t0"]),
                           SourceDoc("arxiv", "2210.03629", "ReAct", "http://a", ["t1"])], [])
    pipeline.digest(di, conn=c, candidate=cand, session_id="s")
    rows = dict(c.execute("SELECT source_id, arxiv_id FROM papers").fetchall())
    assert "Software_agent" in rows and rows["Software_agent"] is None      # wiki: source_id set, arxiv_id NULL
    assert "2210.03629" in rows and rows["2210.03629"] == "2210.03629"      # arxiv: both set
