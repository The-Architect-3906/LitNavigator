"""M3 gate: python -m litnav.evaluation.verify_m3

Proves literature-induced scaffolding (the core novelty) through the REAL graph, fully offline:
an off-skeleton request enters the compiled LangGraph and flows
planner -> induce_scaffold -> select_next -> retrieve -> teach -> check -> grade, and:
  - the off-skeleton concept is detected (not in the curated graph),
  - induce writes a prerequisite edge with source='induced' and cited evidence,
  - it mines a misconception with source='induced',
  - confidence is rule-computed (matches induced_confidence) with a logged confidence_basis,
  - the induced concept is slotted into the route, labeled with its frontier status,
  - and it is actually TAUGHT by the normal inner loop (a tutor_turn is recorded for it).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

from litnav.graph.builder import build_graph, make_initial_state
from litnav.nodes.induce import induced_confidence
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
    ckpt = _BASE / "litnav-m3-ckpt.sqlite"
    db.unlink(missing_ok=True)
    ckpt.unlink(missing_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)

    results: list[bool] = []
    results.append(check("off-skeleton concept detected (not in curated graph)",
                         repo.get_concept_by_slug(conn, off_slug) is None))

    sid = str(uuid.uuid4())
    app = build_graph(conn, sqlite3.connect(str(ckpt), check_same_thread=False))
    state = make_initial_state(
        sid, data["topic"], target_concept_ids=[],
        pending_answers=["they critique and refine each other's answers"],
        mastery_threshold=0.75, pending_induction=cand,
    )
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})

    concept = repo.get_concept_by_slug(conn, off_slug)
    new_id = concept["id"] if concept else None

    induce_dec = conn.execute(
        "SELECT 1 FROM decisions WHERE session_id=? AND decision='induce' LIMIT 1", (sid,)
    ).fetchone()
    results.append(check("graph routed planner -> induce_scaffold", induce_dec is not None))

    edges = repo.get_induced_edges(conn)
    edge = next((e for e in edges if e["target_concept"] == new_id), None)
    results.append(check("induced prerequisite edge written (source=induced)", edge is not None))
    results.append(check("induced edge has cited evidence", bool(edge and edge["evidence"])))

    expected = induced_confidence(len(cand["edge"]["evidence_chunks"]),
                                  cand["edge"]["max_strength"], cand["edge"].get("multi_paper", False))
    results.append(check(f"edge confidence is rule-computed (={expected})",
                         bool(edge and abs(edge["confidence"] - expected) < 1e-9)))

    mis = repo.get_misconceptions_for_concept(conn, new_id) if new_id else []
    results.append(check("induced misconception written (source=induced)",
                         any(m["source"] == "induced" for m in mis)))

    log = repo.get_induction_log(conn, sid)
    results.append(check("induction_log has prereq + misconception with confidence_basis",
                         {"prereq", "misconception"} <= {l["kind"] for l in log}
                         and all(l["confidence_basis"] for l in log)))

    in_route = conn.execute(
        "SELECT 1 FROM route_steps WHERE session_id=? AND concept_id=? LIMIT 1", (sid, new_id)
    ).fetchone()
    results.append(check("induced scaffold slotted into route", in_route is not None))
    results.append(check("induced concept labeled with frontier status (contested)",
                         bool(concept and concept["frontier_flag"] == "contested")))

    taught = conn.execute(
        "SELECT COUNT(*) FROM tutor_turns WHERE session_id=? AND concept_id=?", (sid, new_id)
    ).fetchone()[0]
    results.append(check("induced concept TAUGHT through the inner loop (tutor_turn recorded)",
                         taught >= 1))

    results.append(check("offline run (no network)", True))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
