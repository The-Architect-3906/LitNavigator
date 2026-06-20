"""G-digest: prove the digest pipeline offline. Digest a fixed source slice and assert the written
graph matches the golden graph (concepts as 'digested', the expected typed edge tuples + the prereq
confidence, keypoints), that the edge-accuracy spot-check + unverified flagging are computed, and that
a second identical request hits the cache.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline

_FIX = Path("data/seed/digest_sources_fixture.json")
_GOLD = Path("data/seed/digest_golden_graph.json")


def _load_input(raw: dict) -> tuple[DigestInput, dict]:
    sources = [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
               for s in raw["sources"]]
    return DigestInput(raw["domain_key"], sources, raw.get("target_slugs", [])), raw["candidate"]


def main() -> int:
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    raw = json.loads(_FIX.read_text(encoding="utf-8"))
    gold = json.loads(_GOLD.read_text(encoding="utf-8"))
    di, candidate = _load_input(raw)

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    res = pipeline.digest(di, conn=conn, candidate=candidate, session_id="digest-gate")

    # 1) concepts written as 'digested'
    rows = {r[0]: (r[1], r[2]) for r in
            conn.execute("SELECT slug, source, domain FROM concepts").fetchall()}
    for c in gold["concepts"]:
        assert rows.get(c["slug"]) == (c["source"], c["domain"]), \
            f"concept {c['slug']} mismatch: {rows.get(c['slug'])}"
    print(f"G-digest PASS: {len(gold['concepts'])} concepts written as digested")

    # 2) typed edge tuples present + the prereq confidence (similarity confidence is NOT asserted —
    #    the downgraded 0.55 edge and the native 0.90 edge collide on PK, first writer wins)
    slug = {r[0]: r[1] for r in conn.execute("SELECT id, slug FROM concepts").fetchall()}
    persisted = repo.get_concept_edges(conn, source="digested")
    tuples = {(slug[e["prereq_concept"]], slug[e["target_concept"]], e["edge_type"]) for e in persisted}
    for want in gold["edge_tuples"]:
        assert tuple(want) in tuples, f"missing edge {want}; have {tuples}"
    pe = [e for e in persisted
          if slug[e["prereq_concept"]] == "tool_use" and e["edge_type"] == "prerequisite"][0]
    assert pe["confidence"] == gold["prereq_confidence"], f"prereq conf {pe['confidence']}"
    print(f"G-digest PASS: {len(tuples)} edge tuples persisted; prereq conf={pe['confidence']}")

    # 3) keypoints bound
    all_kp = {k["id"] for cid in slug for k in repo.get_keypoints(conn, cid)}
    for kp in gold["keypoint_ids"]:
        assert kp in all_kp, f"keypoint {kp} missing"
    print(f"G-digest PASS: {len(gold['keypoint_ids'])} keypoints bound")

    # 4) edge-accuracy + unverified flagging — assert the downgrade IDENTITY, not just the count
    assert res.edge_accuracy == gold["edge_accuracy"], f"accuracy {res.edge_accuracy}"
    assert len(res.unverified_edges) == gold["unverified_count"], \
        f"unverified {len(res.unverified_edges)}"
    uv = res.unverified_edges[0]
    assert (uv["prereq_slug"], uv["target_slug"], uv["edge_type"]) == \
        ("reason_act", "self_reflection", "similarity"), f"unexpected downgraded edge {uv}"
    # The downgraded 0.55 prereq edge is written BEFORE the native 0.90 similarity edge and wins the
    # PK (prereq,target,edge_type) collision (INSERT OR IGNORE, first writer wins). Pin that contract.
    sim = [e for e in persisted if slug[e["prereq_concept"]] == "reason_act"
           and slug[e["target_concept"]] == "self_reflection" and e["edge_type"] == "similarity"][0]
    assert sim["confidence"] == gold["downgraded_similarity_confidence"], \
        f"collision survivor conf {sim['confidence']} != {gold['downgraded_similarity_confidence']}"
    print(f"G-digest PASS: edge_accuracy={res.edge_accuracy}, unverified={len(res.unverified_edges)} "
          f"(downgrade identity confirmed; collision survivor conf={sim['confidence']})")

    # 5) second identical request is a cache hit AND does not re-write the graph (no re-digest)
    edges_before = conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0]
    res2 = pipeline.digest(di, conn=conn, candidate=candidate, session_id="digest-gate")
    assert res2.cache_hit is True
    assert conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0] == edges_before, \
        "cache hit must not re-write the graph"
    print("G-digest PASS: identical slice is a cache hit (graph unmutated)")

    print("G-digest: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
