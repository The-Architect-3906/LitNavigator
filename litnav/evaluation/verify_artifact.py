"""G-artifact (offline determinism/schema UNIT gate) — NOT capability evidence.
Validates deterministic ARTIFACT logic: selector matrix, mindmap renderer,
make_artifact end-to-end offline (mindmap + combination), cross-cutting
citations/retrieval-prompt invariant. The CAPABILITY is proven by verify_artifact_live."""
from __future__ import annotations
import os, sqlite3, tempfile
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.artifact.selector import select_format
from litnav.artifact.renderers import mindmap
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact


def _seed_db(c: sqlite3.Connection) -> None:
    """Seed an in-memory DB with two concepts, one edge, one paper, two chunks."""
    repo.create_session(c, "s", topic="t")
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'a', 'A')")
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (2, 'b', 'B')")
    c.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (2, 1, 'prerequisite')"
    )
    c.execute(
        "INSERT INTO papers (id, title) VALUES (1, 'Test Paper')"
    )
    c.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, chunk_index, text) VALUES ('c0', 1, 1, 0, 'Evidence for A.')"
    )
    c.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, chunk_index, text) VALUES ('c1', 1, 2, 0, 'Evidence for B.')"
    )
    c.commit()


def main() -> int:
    os.environ["LITNAV_LLM_PROVIDER"] = "none"

    # ── Selector matrix ───────────────────────────────────────────────────────
    assert select_format({"goal_type": "survey", "content_kind": "structure", "user_request": ""}) == "mindmap"
    assert select_format({"goal_type": None, "content_kind": "present", "user_request": "make a deck"}) == "slides"
    assert select_format({"goal_type": "functional", "content_kind": "procedure", "user_request": "how to build X"}) == "worked_example"
    assert select_format({"goal_type": "mastery", "content_kind": "reference", "user_request": "recall"}) == "combination"
    assert select_format({"goal_type": None, "content_kind": "reference", "user_request": "crash course"}) == "notes"
    # override wins
    assert select_format({"goal_type": "survey"}, override="notes") == "notes"
    print("G-artifact PASS: selector matrix (6 cases + override)")

    # ── mindmap renderer from fixture graph ───────────────────────────────────
    graph = {
        "concepts": [{"slug": "a", "name": "A"}, {"slug": "b", "name": "B"}],
        "edges": [{"prereq_slug": "b", "target_slug": "a", "edge_type": "prerequisite"}],
    }
    mm = mindmap.render(graph, ["c0"])
    assert "mermaid" in mm, "mindmap body must contain 'mermaid'"
    assert "b --> a" in mm, "mindmap must have prerequisite arrow b --> a"
    assert "recall" in mm.lower(), "mindmap must contain a retrieval prompt (recall)"
    assert "c0" in mm, "mindmap must list citation c0"
    print("G-artifact PASS: mindmap renderer (mermaid + arrow + recall prompt + citation)")

    # ── make_artifact end-to-end offline: mindmap ─────────────────────────────
    c = sqlite3.connect(":memory:")
    init_db(c)
    _seed_db(c)
    out1 = tempfile.mkdtemp()
    res = make_artifact(
        ArtifactInput([1, 2], {"goal_type": "survey", "content_kind": "structure", "user_request": ""}),
        conn=c, session_id="s", out_dir=out1,
    )
    import os as _os
    assert _os.path.isfile(res.artifact_path), "artifact file must exist"
    assert res.artifact_path.endswith(".md"), "artifact must be a .md file"
    body = open(res.artifact_path, encoding="utf-8").read()
    assert "mermaid" in body, "mindmap artifact body must contain 'mermaid'"
    assert res.citations, "mindmap artifact must have non-empty citations"
    print(f"G-artifact PASS: make_artifact mindmap offline → {res.artifact_path}")

    # ── make_artifact end-to-end offline: combination ─────────────────────────
    out2 = tempfile.mkdtemp()
    res2 = make_artifact(
        ArtifactInput([1, 2], {"goal_type": "mastery", "content_kind": "reference", "user_request": "recall"},
                      format="combination"),
        conn=c, session_id="s", out_dir=out2,
    )
    assert _os.path.isfile(res2.artifact_path), "combination artifact file must exist"
    assert res2.format == "combination"
    body2 = open(res2.artifact_path, encoding="utf-8").read()
    assert "mermaid" in body2, "combination must contain mindmap section"
    assert "Study Notes" in body2, "combination must contain Study notes section"
    assert "Worked Example" in body2, "combination must contain Worked Example section"
    assert "c0" in body2, "combination must cite c0"
    print(f"G-artifact PASS: make_artifact combination offline (3 sections + c0)")

    # ── cross-cutting invariant: citations section + retrieval prompt ──────────
    assert "Citations" in body2, "combination must have Citations section"
    body2_lower = body2.lower()
    assert any(w in body2_lower for w in ("recall", "retrieval", "test yourself")), \
        "combination must contain a retrieval prompt"
    print("G-artifact PASS: cross-cutting invariant (Citations + retrieval prompt in combination)")

    print("G-artifact: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
