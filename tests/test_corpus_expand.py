# tests/test_corpus_expand.py
import json
from litnav.ingest import corpus_expand as ce


def test_nearest_concept_picks_highest_cosine():
    centroids = {1: [1.0, 0.0], 2: [0.0, 1.0]}
    assert ce._nearest_concept([0.9, 0.1], centroids) == 1
    assert ce._nearest_concept([0.1, 0.9], centroids) == 2


def test_build_expanded_fixture_tags_and_appends(tmp_path, monkeypatch):
    """New papers' chunks are tagged to the nearest concept and appended; spine preserved."""
    # Concept-name embeddings: 'react' name -> [1,0]; all other names + chunks -> [0,1],
    # except a chunk containing 'reason' -> [1,0] so it tags to react.
    def fake_embed(texts):
        out = []
        for t in texts:
            low = t.lower()
            out.append([1.0, 0.0] if ("react" in low or "reason" in low) else [0.0, 1.0])
        return out
    monkeypatch.setattr(ce.llm_client, "embed_texts", fake_embed)

    papers = [{"arxiv_id": "9999.00001", "title": "A ReAct follow-up",
               "chunks": ["This work reasons then acts.", "Unrelated memory text."]}]
    out = tmp_path / "agents_expanded.json"
    n = ce.build_expanded_fixture("data/seed/agents_m3.json", papers, str(out))
    assert n == 2

    data = json.loads(out.read_text(encoding="utf-8"))
    base = json.loads(open("data/seed/agents_m3.json", encoding="utf-8").read())
    assert len(data["concepts"]) == len(base["concepts"])          # spine preserved
    assert "induction" in data                                     # induction candidate kept
    new = [c for c in data["chunks"] if c["id"].startswith("cx_9999.00001")]
    assert len(new) == 2 and all(c["concept_id"] is not None for c in new)
    react_id = next(c["id"] for c in data["concepts"] if c["slug"] == "react")
    assert new[0]["concept_id"] == react_id                        # 'reasons then acts' -> react
