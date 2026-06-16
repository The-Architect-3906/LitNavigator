"""M2 gate: python -m litnav.evaluation.verify_m2

Runs the agent-domain tutor loop through the compiled LangGraph and asserts:
  - teaching cites real chunk evidence,
  - the ReAct=CoT misconception is detected on a wrong answer,
  - reteach switches to a different explanation strategy,
  - a reteach turn shows a learning gain (post > pre),
  - confidence stays calibrated (below mastery while observations are few),
  - the exhausted-reteach path concedes honestly instead of looping,
  - a correct first answer advances WITHOUT any reteach (counterfactual).

All checks run fully offline (LITNAV_LLM_PROVIDER=none fixture path).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_m2.json"
_BASE = Path("data/runtime")
THRESHOLD = 0.75
WRONG = "it just uses chain of thought reasoning"
CORRECT = "the agent takes actions and observations from the environment"


def check(label: str, condition: bool) -> bool:
    print(f"G2 PASS: {label}" if condition else f"G2 FAIL: {label}",
          file=sys.stdout if condition else sys.stderr)
    return bool(condition)


def _setup(name: str) -> sqlite3.Connection:
    _BASE.mkdir(parents=True, exist_ok=True)
    db = _BASE / f"litnav-m2-{name}.sqlite"
    db.unlink(missing_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, FIXTURE)
    return conn


def _ckpt(name: str) -> sqlite3.Connection:
    p = _BASE / f"litnav-m2-{name}-ckpt.sqlite"
    p.unlink(missing_ok=True)
    return sqlite3.connect(str(p), check_same_thread=False)


def _run(name: str, answers: list[str], react_id: int, topic: str):
    conn = _setup(name)
    app = build_graph(conn, _ckpt(name))
    sid = str(uuid.uuid4())
    state = make_initial_state(sid, topic, [react_id],
                               pending_answers=answers, mastery_threshold=THRESHOLD)
    app.invoke(state, config={"configurable": {"thread_id": sid}, "recursion_limit": 50})
    return conn, sid


def main() -> int:
    data = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    topic = data["topic"]
    react_id = {c["slug"]: c["id"] for c in data["concepts"]}["react"]
    results: list[bool] = []

    # ── Scenario A: misconception -> reteach -> pass ────────────────────────────
    conn, sid = _run("reteach", [WRONG, CORRECT], react_id, topic)

    turns = conn.execute(
        "SELECT turn_type, strategy, pre_check_score, post_check_score, cited_chunks "
        "FROM tutor_turns WHERE session_id=? ORDER BY id", (sid,)
    ).fetchall()
    results.append(check("teaching cites evidence",
                         any(json.loads(t[4]) for t in turns)))

    det = conn.execute(
        "SELECT detected_misconception FROM quiz_attempts "
        "WHERE session_id=? AND detected_misconception IS NOT NULL", (sid,)
    ).fetchall()
    results.append(check("misconception detected",
                         any(r[0] == "react_is_just_cot" for r in det)))

    ls = conn.execute(
        "SELECT tried_strategies, mastery, confidence FROM learner_state "
        "WHERE session_id=? AND concept_id=?", (sid, react_id)
    ).fetchone()
    tried = json.loads(ls[0] or "[]")
    results.append(check("reteach strategy switched (>=2 distinct)", len(set(tried)) >= 2))

    reteach_turns = [t for t in turns if t[0] == "reteach"]
    results.append(check("learning gain: reteach post > pre",
                         bool(reteach_turns) and
                         reteach_turns[0][3] > (reteach_turns[0][2] or 0.0)))

    results.append(check("mastery crossed threshold after reteach", ls[1] >= THRESHOLD))
    results.append(check("confidence calibrated (below mastery)", ls[2] < ls[1]))

    react_step = conn.execute(
        "SELECT status FROM route_steps WHERE session_id=? AND concept_id=? "
        "ORDER BY route_version DESC LIMIT 1", (sid, react_id)
    ).fetchone()
    results.append(check("react step marked done after reteach", react_step and react_step[0] == "done"))

    # ── Scenario B: exhausted reteach -> concede (no infinite loop) ─────────────
    conn_b, sid_b = _run("concede", [WRONG, WRONG, WRONG], react_id, topic)
    concede_dec = conn_b.execute(
        "SELECT 1 FROM decisions WHERE session_id=? AND decision='concede' LIMIT 1", (sid_b,)
    ).fetchone()
    results.append(check("concede terminates exhausted reteach loop", concede_dec is not None))
    conceded_step = conn_b.execute(
        "SELECT status FROM route_steps WHERE session_id=? AND concept_id=? "
        "ORDER BY route_version DESC LIMIT 1", (sid_b, react_id)
    ).fetchone()
    results.append(check("conceded concept does not loop (step conceded)",
                         conceded_step and conceded_step[0] == "conceded"))

    # ── Scenario C (counterfactual): correct first answer advances, no reteach ──
    conn_c, sid_c = _run("direct", [CORRECT], react_id, topic)
    n_reteach = conn_c.execute(
        "SELECT COUNT(*) FROM decisions WHERE session_id=? AND decision='reteach'", (sid_c,)
    ).fetchone()[0]
    results.append(check("correct answer advances without reteach", n_reteach == 0))

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
