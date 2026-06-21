"""G-openworld-e2e-live (LIVE): the WHOLE open-world chain on a fresh real topic, asserting on the
PERSISTED graph + real artifacts — not in-memory returns. Skips at provider=none.

This is the gate the earlier per-stage live gates missed: it runs discover -> digest -> teach ->
make-artifact on a topic outside every fixture and asserts (1) concepts actually PERSIST to the DB,
(2) keypoint evidence resolves to real chunks, (3) quiz items persist with valid concept FKs, and
(4) artifacts render NON-EMPTY and GROUNDED with citations that resolve to real chunks. A green run
here means a real learner could be taught from a freshly digested topic end-to-end.
"""
from __future__ import annotations
import os, sqlite3, tempfile
from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.discover.contract import DiscoverInput
from litnav.discover import find_sources
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.nodes import goal_elicit
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact
from litnav.llm import client as llm_client

_TOPIC = "variational autoencoders in deep learning"      # outside every fixture
_BUDGET = 80000
_EMPTY = {"concepts": [], "keypoints": [], "prereq_edges": [], "similarity_edges": [],
          "quiz_seeds": [], "judge_labels": {}}


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-openworld-e2e-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "e2e", topic=_TOPIC)

    # 1) DISCOVER (OW-3)
    res = find_sources.find(DiscoverInput(_TOPIC, k=6), conn=c, session_id="e2e", budget=_BUDGET)
    withft = [s for s in res.sources if s.chunks and sum(len(x) for x in s.chunks) > 200]
    assert withft, "FAIL: no discovered source had real full text"
    print(f"G-openworld-e2e-live PASS: discover {len(res.sources)} sources, intent={res.intent_used}")

    # 2) DIGEST (OW-2/1) — then assert the PERSISTED graph (not the in-memory return)
    top = max(withft, key=lambda s: sum(len(x) for x in s.chunks))
    di = DigestInput(_TOPIC, [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                     target_slugs=[])
    pipeline.digest(di, conn=c, candidate=_EMPTY, session_id="e2e", budget=_BUDGET)
    assert llm_client.was_live(), "FAIL: digest did not run live"
    db_concepts = c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    assert db_concepts >= 2, f"FAIL: only {db_concepts} concepts PERSISTED"
    unresolved_kp = c.execute(
        "SELECT COUNT(*) FROM keypoints kp LEFT JOIN paper_chunks pc ON pc.id = kp.evidence_chunk_id "
        "WHERE kp.evidence_chunk_id IS NOT NULL AND pc.id IS NULL").fetchone()[0]
    assert unresolved_kp == 0, f"FAIL: {unresolved_kp} keypoints have unresolved evidence"
    orphan_quiz = c.execute(
        "SELECT COUNT(*) FROM quiz_items q LEFT JOIN concepts cc ON cc.id = q.concept_id "
        "WHERE cc.id IS NULL").fetchone()[0]
    assert orphan_quiz == 0, f"FAIL: {orphan_quiz} quiz_items orphaned at a non-existent concept_id"
    print(f"G-openworld-e2e-live PASS: {db_concepts} concepts PERSISTED, keypoint evidence + quiz FKs valid")

    # 3) TEACH (OW-4): goal elicitation runs live on the fresh topic
    gt = goal_elicit.classify_goal("I want to deeply master " + _TOPIC, conn=c, session_id="e2e")
    assert gt in {"mastery", "functional", "survey"}, f"FAIL: bad goal_type {gt!r}"
    print(f"G-openworld-e2e-live PASS: goal classified live = {gt!r}")

    # 4) MAKE-ARTIFACT (OW-5): non-empty + grounded + resolving citations on the digested graph
    ids = [r[0] for r in c.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:4]
    valid_chunks = {r[0] for r in c.execute("SELECT id FROM paper_chunks").fetchall()}
    od = tempfile.mkdtemp()
    for fmt in ("notes", "slides", "mindmap"):
        r = make_artifact(ArtifactInput(ids, {"goal_type": gt}, format=fmt),
                          conn=c, session_id="e2e", out_dir=od)
        body = open(r.artifact_path, encoding="utf-8").read()
        assert len(body) > 80, f"FAIL: {fmt} artifact effectively empty ({len(body)} chars)"
        assert r.citations, f"FAIL: {fmt} produced no citations (ungrounded)"
        assert all(cit in valid_chunks for cit in r.citations), f"FAIL: {fmt} citations don't resolve"
        print(f"G-openworld-e2e-live PASS: {fmt} non-empty ({len(body)} chars), citations resolve {r.citations}")

    spend = cost_repo.session_spend(c, "e2e")
    assert spend["tokens"] > 0
    print("--- COST ledger ---")
    for row in c.execute("SELECT stage,tier,model,SUM(total_tokens),ROUND(SUM(usd),6),COUNT(*) "
                         "FROM cost_ledger GROUP BY stage,tier,model ORDER BY SUM(usd) DESC"):
        print("  ", tuple(row))
    print(f"G-openworld-e2e-live: ALL PASS (total usd={spend['usd']})"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
