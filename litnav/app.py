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
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from litnav.config import DEMO_DB_PATH
from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage import repo
from litnav.storage.schema import init_db, reset_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.trace import build_trace

_M1_FIXTURE = "data/seed/rag_demo.json"
_M2_FIXTURE = "data/seed/agents_m2.json"
_M3_FIXTURE = "data/seed/agents_m3.json"
_CORPUS_FIXTURE = "data/seed/agents_corpus.json"

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


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID is currently running. Cross-platform and SAFE —
    never signals/terminates the target (notably, os.kill(pid, 0) would TERMINATE on
    Windows, so we use OpenProcess there)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False  # no such process (or not ours) -> treat as gone
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by someone else
    return True


def _lock_holder_pid(lock_path: Path) -> int | None:
    """PID recorded in the lock file, or None if absent/empty/unreadable."""
    try:
        text = lock_path.read_text().strip()
        return int(text) if text else None
    except (FileNotFoundError, ValueError, OSError):
        return None


@contextmanager
def _demo_db_lock(timeout: float = 120.0):
    """Serialize concurrent CLI demos against the shared demo DB.

    Every demo run resets the demo DB in place (drop+recreate). Running two demos at once
    let one process drop tables mid-run in another ('no such table: route_steps'). This
    cross-platform lockfile (O_CREAT|O_EXCL) makes concurrent runs wait their turn.

    Stale-lock handling is liveness-based, not time-based: the lock records the holder's
    PID, and we only reclaim it when that process is actually gone (a crashed run). A live
    holder is NEVER stolen — so a slow live-LLM demo that runs past any timeout keeps its
    lock. If a live holder is still busy after `timeout`, we raise a clear error instead of
    stealing (so two demos never end up racing on the shared DB)."""
    lock_path = Path(DEMO_DB_PATH).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    start = time.monotonic()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())  # record holder for liveness checks
            break
        except FileExistsError:
            holder = _lock_holder_pid(lock_path)
            if holder is not None and not _pid_alive(holder):
                try:                                  # holder crashed -> reclaim its lock
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() - start > timeout:
                raise RuntimeError(
                    f"Demo DB is locked by a running demo (PID {holder}) and still busy "
                    f"after {timeout:.0f}s. Wait for it to finish and retry, or delete "
                    f"{lock_path} if that process is gone.")
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _fresh_db() -> tuple[sqlite3.Connection, sqlite3.Connection, str]:
    """Open a fresh demo DB. Resets the demo DB IN PLACE (drop+recreate, no file unlink)
    so a run can't hit a Windows PermissionError when the panel still has the file open.
    The checkpoint is in-memory: a CLI demo is one-shot and needs no persistent checkpoint."""
    db_path = Path(DEMO_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    reset_db(conn)
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    return conn, ckpt, str(db_path)


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


def _run_m3(requested_concept: str = "multi_agent_debate") -> None:
    """M3: an off-skeleton request enters the graph (planner -> induce_scaffold ->
    select_next -> retrieve -> teach -> check -> grade), inducing then teaching the concept."""
    conn, ckpt, db_path = _fresh_db()
    init_db(conn)
    seed_demo_data(conn, _M3_FIXTURE)
    data = json.loads(Path(_M3_FIXTURE).read_text(encoding="utf-8"))
    cand = data["induction"]
    off_slug = cand["off_skeleton"]["slug"]
    if requested_concept != off_slug:
        print(f"(note: only '{off_slug}' has a prepared induction candidate in this fixture; inducing it.)")

    sid = str(uuid.uuid4())
    app = build_graph(conn, ckpt)
    state = make_initial_state(
        sid, data["topic"], target_concept_ids=[],
        pending_answers=["they critique and refine each other's answers"],
        mastery_threshold=0.75, pending_induction=cand,
    )
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})

    print(f"\nSession:        {sid}  ({data['topic']})")
    print(f"Off-skeleton request: '{off_slug}' is NOT in the curated graph -> induce_scaffold")
    print("\nInduced scaffolding (source=induced, confidence rule-computed):")
    for log in repo.get_induction_log(conn, sid):
        print(f"  [{log['kind']}] confidence={log['confidence']}  basis={log['confidence_basis']}  "
              f"evidence={log['evidence_chunks']}")
    _print_trace(conn, sid, db_path)


def _plan_for_intent(conn: sqlite3.Connection, topic: str, intent: str):
    from litnav.nodes.planner import planner_node
    sid = str(uuid.uuid4())
    state = make_initial_state(sid, topic, target_concept_ids=[], intent=intent)
    out = planner_node(state, conn)
    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM concepts")}
    route = [names.get(s["concept_id"], s["concept_id"]) for s in out["route"]]
    return state["mastery_threshold"], state["teach_depth"], route


def _run_intent(which: str | None) -> None:
    """Show how the same corpus is re-scoped to different purposes (intent modes)."""
    from litnav.intent import INTENTS
    conn, _ckpt, _db = _fresh_db()
    init_db(conn)
    seed_demo_data(conn, _CORPUS_FIXTURE)
    data = json.loads(Path(_CORPUS_FIXTURE).read_text(encoding="utf-8"))
    intents = [which] if which else list(INTENTS)
    print(f"\nSame corpus ('{data['topic']}'), re-scoped by intent:\n")
    for it in intents:
        thr, depth, route = _plan_for_intent(conn, data["topic"], it)
        print(f"[{it}] {INTENTS[it]['label']}  (mastery bar {thr}, depth {depth})")
        print("  route: " + " -> ".join(route) + "\n")


def main() -> int:
    from litnav.config import load_dotenv
    load_dotenv()  # pick up LITNAV_LLM_* / OPENAI_API_KEY from .env for live runs
    parser = argparse.ArgumentParser(prog="litnav.app")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("demo-m1"); p1.add_argument("--answer", default="wrong_prereq",
                                                    choices=sorted(_M1_ANSWERS))
    p2 = sub.add_parser("demo-m2"); p2.add_argument("--answer", default="cot",
                                                    choices=sorted(_M2_ANSWERS))
    p3 = sub.add_parser("demo-m3"); p3.add_argument("--concept", default="multi_agent_debate")
    p4 = sub.add_parser("demo-intent")
    p4.add_argument("--intent", choices=["researcher", "journalist"], default=None,
                    help="show one intent; omit to compare both")
    args = parser.parse_args()

    # All demos write to the one shared demo DB (so the panel can render the latest run);
    # serialize concurrent invocations so one run's reset_db() can't drop tables mid-run.
    with _demo_db_lock():
        if args.command == "demo-m1":
            _run(_M1_FIXTURE, _M1_ANSWERS[args.answer],
                 targets=["dense_retrieval", "contrastive_learning"], threshold=0.8)
        elif args.command == "demo-m2":
            _run(_M2_FIXTURE, _M2_ANSWERS[args.answer], targets=["react"], threshold=0.75)
        elif args.command == "demo-m3":
            _run_m3(args.concept)
        elif args.command == "demo-intent":
            _run_intent(args.intent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
