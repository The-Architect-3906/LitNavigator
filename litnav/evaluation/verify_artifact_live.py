"""G-artifact-live (LIVE): prove ARTIFACT works on a real provider. Skips at provider=none."""
from __future__ import annotations
import os, sqlite3, tempfile
from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact
from litnav.llm import client as llm_client


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-artifact-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"

    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")

    # Seed: two concepts (react / tool_use), one paper, two chunks, one prerequisite edge
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (1, 'react', 'ReAct')")
    c.execute("INSERT INTO concepts (id, slug, name) VALUES (2, 'tool_use', 'Tool Use')")
    c.execute(
        "INSERT INTO concept_edges (prereq_concept, target_concept, edge_type) VALUES (2, 1, 'prerequisite')"
    )
    c.execute("INSERT INTO papers (id, title) VALUES (1, 'ReAct: Synergizing Reasoning and Acting')")
    c.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, chunk_index, text) VALUES "
        "('c0', 1, 1, 0, 'ReAct interleaves reasoning traces with actions, allowing agents to plan, act, and observe in a loop.')"
    )
    c.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, chunk_index, text) VALUES "
        "('c1', 1, 2, 0, 'Tool use enables language models to call external APIs or code executors to retrieve information or perform computation.')"
    )
    c.commit()

    live_checked = False
    for fmt in ("notes", "slides", "worked_example"):
        out = tempfile.mkdtemp()
        res = make_artifact(
            ArtifactInput([1, 2], {"goal_type": "mastery"}, format=fmt),
            conn=c, session_id="s", out_dir=out,
        )
        assert os.path.isfile(res.artifact_path) and os.path.getsize(res.artifact_path) > 0, \
            f"FAIL: artifact file missing or empty for fmt={fmt}"
        assert res.format == fmt, f"FAIL: format mismatch: expected {fmt!r}, got {res.format!r}"
        assert res.citations, f"FAIL: no citations for fmt={fmt}"
        for cid in res.citations:
            count = c.execute(
                "SELECT COUNT(*) FROM paper_chunks WHERE id=?", (cid,)
            ).fetchone()[0]
            assert count == 1, f"FAIL: citation {cid!r} does not resolve to a real chunk"
        body = open(res.artifact_path, encoding="utf-8").read().lower()
        assert any(w in body for w in ("recall", "retrieval", "test yourself")), \
            f"FAIL: no retrieval prompt in {fmt} artifact"
        if not live_checked:
            assert llm_client.was_live(), f"FAIL: first live render ({fmt}) was not live"
            live_checked = True
        print(f"G-artifact-live PASS: {fmt} → {res.artifact_path} citations={res.citations}")

    # Artifact spend metered
    artifact_rows = c.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE stage='artifact'"
    ).fetchone()[0]
    assert artifact_rows >= 1, "FAIL: artifact spend not metered in cost_ledger"
    spend = cost_repo.session_spend(c, "s")
    assert spend["tokens"] > 0, f"FAIL: no live spend recorded; spend={spend}"
    print(f"G-artifact-live PASS: artifact metered; total spend usd={spend['usd']}")

    print("--- COST ledger ---")
    for row in c.execute(
        "SELECT stage, tier, model, SUM(total_tokens), ROUND(SUM(usd), 6), COUNT(*) "
        "FROM cost_ledger GROUP BY stage, tier, model ORDER BY stage"
    ):
        print("  ", tuple(row))

    print("G-artifact-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
