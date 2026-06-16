"""CLI debug runner for the LitNavigator demos.

    python -m litnav.app demo-m1 --answer wrong_prereq   # route replans on a prereq gap
    python -m litnav.app demo-m1 --answer correct        # advances cleanly
    python -m litnav.app demo-m2 --answer cot            # misconception -> reteach -> pass
    python -m litnav.app demo-m2 --answer correct        # advances without reteach
    python -m litnav.app demo-m2 --answer exhausted      # reteach exhausted -> honest concede

Each run writes the trace into the demo SQLite (LITNAV_DB_PATH); launch
`python -m litnav.ui.server` and open the printed URL to see the visual panel.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from pathlib import Path

from litnav.config import DEMO_CKPT_PATH, DEMO_DB_PATH
from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.trace import build_trace

_M1_FIXTURE = "data/seed/rag_demo.json"
_M2_FIXTURE = "data/seed/agents_m2.json"

# answer keyword -> ordered pending answers fed to the grader
_M1_ANSWERS = {
    "wrong_prereq": ["embedding vectors", "keyword matching"],
    "correct": ["embedding vectors", "they are pulled together"],
}
_M2_ANSWERS = {
    "cot": ["it just uses chain of thought reasoning", "the agent takes actions and observations"],
    "correct": ["the agent takes actions and observations"],
    "exhausted": ["chain of thought", "chain of thought", "chain of thought"],
}


def _fresh_db() -> tuple[sqlite3.Connection, sqlite3.Connection, str]:
    """Open fresh demo databases. Only the dedicated demo files are ever deleted,
    so this never touches whatever LITNAV_DB_PATH points at."""
    db_path = Path(DEMO_DB_PATH)
    ckpt = Path(DEMO_CKPT_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    ckpt.unlink(missing_ok=True)
    return (sqlite3.connect(str(db_path), check_same_thread=False),
            sqlite3.connect(str(ckpt), check_same_thread=False),
            str(db_path))


def _print_trace(conn: sqlite3.Connection, sid: str, db_path: str) -> None:
    t = build_trace(conn, sid)
    print(f"\nSession:       {sid}  ({t['session'].get('topic')})")
    print(f"Route (v{t['route_version']}):  " +
          " | ".join(f"{s['name']}[{s['status']}]" for s in t["route"]))

    # Turn-by-turn: build_trace.timeline already pairs each teaching turn with the
    # answer, the learner state after, and the decision it triggered (real stored values).
    print("\nTurn-by-turn:")
    for ev in t["timeline"]:
        print(f"\n  [{ev['index']}] {ev['name']} - {ev['turn_type']}/{ev['strategy']}  "
              f"cites={ev['cited_chunks']}")
        if ev["answer"] is not None:
            mark = "correct" if ev["score"] == 1.0 else "wrong"
            print(f"      answer:  {ev['answer']!r}  ->  {mark} (score={ev['score']})"
                  + (f"   misconception: {ev['detected_misconception']}"
                     if ev["detected_misconception"] else ""))
        print(f"      learner: mastery={ev['mastery_after']} confidence={ev['confidence_after']}")
        if ev["decision"] is not None:
            print(f"      -> decision: {ev['decision']} - {ev['rationale']}")

    print("\nFinal learner model:")
    for c in t["concepts"]:
        if c["n_observations"]:
            print(f"  - {c['name']}: mastery={c['mastery']} confidence={c['confidence']} "
                  f"({c['n_observations']} obs) held={c['held_misconceptions']}")
    print(f"\nView the panel:  python -m litnav.ui.server   then open  http://127.0.0.1:8000/sessions/{sid}")
    print(f"(demo DB: {db_path})")


def _run(fixture: str, answers: list[str], targets: list[str], threshold: float) -> None:
    conn, ckpt, db_path = _fresh_db()
    init_db(conn)
    seed_demo_data(conn, fixture)
    data = json.loads(Path(fixture).read_text(encoding="utf-8"))
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    target_ids = [slug_to_id[s] for s in targets]

    app = build_graph(conn, ckpt)
    sid = str(uuid.uuid4())
    state = make_initial_state(sid, data["topic"], target_ids,
                               pending_answers=answers, mastery_threshold=threshold)
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    _print_trace(conn, sid, db_path)


def main() -> int:
    parser = argparse.ArgumentParser(prog="litnav.app")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("demo-m1"); p1.add_argument("--answer", default="wrong_prereq",
                                                    choices=sorted(_M1_ANSWERS))
    p2 = sub.add_parser("demo-m2"); p2.add_argument("--answer", default="cot",
                                                    choices=sorted(_M2_ANSWERS))
    args = parser.parse_args()

    if args.command == "demo-m1":
        _run(_M1_FIXTURE, _M1_ANSWERS[args.answer],
             targets=["dense_retrieval", "contrastive_learning"], threshold=0.8)
    elif args.command == "demo-m2":
        _run(_M2_FIXTURE, _M2_ANSWERS[args.answer], targets=["react"], threshold=0.75)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
