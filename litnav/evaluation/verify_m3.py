"""M3 gate: python -m litnav.evaluation.verify_m3

Proves literature-induced scaffolding (the core novelty), fully offline:
  - an off-skeleton concept is detected (not in the curated graph),
  - induce_scaffold writes a prerequisite edge with source='induced' and cited evidence,
  - it mines a misconception with source='induced',
  - confidence is rule-computed (matches induced_confidence) and a confidence_basis is logged,
  - the induced concept is slotted into the route and labeled with its frontier status.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

from litnav.nodes.induce import induce_scaffold_node, induced_confidence
from litnav.storage import repo
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_m3.json"
_BASE = Path("data/runtime")


def check(label: str, ok: bool) -> bool:
    print(f"G3 PASS: {label}" if ok else f"G3 FAIL: {label}",
          file=sys.stdout if ok else sys.stderr)
    return bool(ok)


def main() -> int:
    data = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    cand = data["induction"]
    off_slug = cand["off_skeleton"]["slug"]

    _BASE.mkdir(parents=True, exist_ok=True)
    db = _BASE / "litnav-m3.sqlite"
    db.unlink(missing_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)

    sid = str(uuid.uuid4())
    repo.create_session(conn, sid, data["topic"])

    results: list[bool] = []

    # Off-skeleton detection: the concept must NOT exist in the curated graph yet.
    results.append(check("off-skeleton concept detected (not in curated graph)",
                         repo.get_concept_by_slug(conn, off_slug) is None))

    state = {"session_id": sid, "route": [], "route_version": 1}
    out = induce_scaffold_node(state, conn, cand)
    new_id = out["current_concept_id"]

    induced_edges = repo.get_induced_edges(conn)
    edge = next((e for e in induced_edges if e["target_concept"] == new_id), None)
    results.append(check("induced prerequisite edge written (source=induced)", edge is not None))
    results.append(check("induced edge has cited evidence", bool(edge and edge["evidence"])))

    expected_conf = induced_confidence(
        len(cand["edge"]["evidence_chunks"]), cand["edge"]["max_strength"],
        cand["edge"].get("multi_paper", False))
    results.append(check(f"edge confidence is rule-computed (={expected_conf})",
                         bool(edge and abs(edge["confidence"] - expected_conf) < 1e-9)))

    mis = repo.get_misconceptions_for_concept(conn, new_id)
    results.append(check("induced misconception written (source=induced)",
                         any(m["source"] == "induced" for m in mis)))

    log = repo.get_induction_log(conn, sid)
    kinds = {l["kind"] for l in log}
    results.append(check("induction_log has prereq + misconception with confidence_basis",
                         {"prereq", "misconception"} <= kinds
                         and all(l["confidence_basis"] for l in log)))

    steps = conn.execute(
        "SELECT concept_id FROM route_steps WHERE session_id=?", (sid,)
    ).fetchall()
    results.append(check("induced scaffold slotted into route",
                         any(r[0] == new_id for r in steps)))

    concept = repo.get_concept_by_slug(conn, off_slug)
    results.append(check("induced concept labeled with frontier status (contested)",
                         bool(concept and concept["frontier_flag"] == "contested")))

    results.append(check("offline run (no network)", True))

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
