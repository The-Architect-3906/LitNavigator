import os, sqlite3
from litnav.storage.schema import init_db
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact

def _seed(c):
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1,'react','ReAct'),(2,'tool_use','Tool Use')")
    c.execute("INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (2,1,'prerequisite')")
    c.execute("INSERT INTO papers (id, title) VALUES (1,'P')")
    c.execute("INSERT INTO paper_chunks (id, paper_id, concept_id, chunk_index, text) VALUES "
              "('c0',1,1,0,'ReAct interleaves reasoning and acting.'),"
              "('c1',1,2,0,'Tools let an agent act on the world.')")
    c.commit()

def test_make_artifact_mindmap_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); _seed(c)
    ai = ArtifactInput(concept_ids=[1, 2], scenario={"goal_type": "survey", "content_kind": "structure", "user_request": ""})
    res = make_artifact(ai, conn=c, session_id="s", out_dir=str(tmp_path))
    assert res.format == "mindmap"
    assert os.path.exists(res.artifact_path) and res.artifact_path.endswith(".md")
    body = open(res.artifact_path, encoding="utf-8").read()
    assert "mermaid" in body and "ReAct" in body
    assert res.citations and "c0" in res.citations          # evidence → citations

def test_make_artifact_override_and_combination(tmp_path, monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c); _seed(c)
    ai = ArtifactInput(concept_ids=[1, 2], scenario={"goal_type": "mastery"}, format="combination")
    res = make_artifact(ai, conn=c, session_id="s", out_dir=str(tmp_path))
    assert res.format == "combination"
    body = open(res.artifact_path, encoding="utf-8").read()
    assert "mermaid" in body                 # map section
    assert "Study notes" in body             # notes section
    assert "Worked Example" in body          # worked section
    assert "c0" in body                       # citations carried
