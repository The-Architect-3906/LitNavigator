"""G-live-tutor (opt-in LIVE): drive a REAL keypoint (ORIENT->TEACH->ASSESS) session on the live model
and assert the invariants that shipped broken because the offline suite only exercises the deterministic
fallback grader. Each maps to a bug that was 'green offline, broken live':

  BUG 1  mastery must be written back to learner_state    -> mastery rises after correct answers
  N1     grading must accept key-idea paraphrases         -> a correct paraphrase is graded correct
  BUG 5  a wrong answer voicing a misconception is named  -> detected_misconception is non-null
  BUG 3  quizzes escalate Bloom level                     -> a question past 'recall' is posed

Advance-vs-concede (BUG 2) is rule-computed (not LLM-dependent) and fully covered offline by
tests/test_keypoint_flow.py, so it is not re-run live here.

Run: LITNAV_LIVE_GATES=1 LITNAV_LLM_PROVIDER=openai LITNAV_LLM_API_KEY=... \
     .venv/bin/python -m litnav.evaluation.verify_live_tutor
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from litnav.config import load_dotenv
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession
from litnav.evaluation.live_harness import Gate, k_of_n, live_enabled

# Teach on the fixture the UI actually serves.
_FIXTURE = ("data/seed/agents_expanded.json"
            if Path("data/seed/agents_expanded.json").exists() else "data/seed/agents_m3.json")

# Answers chosen to be robustly correct / wrong for ReAct regardless of the live-generated question.
_CORRECT = ("ReAct interleaves the model's reasoning traces with actions and observations from the "
            "environment, so the agent grounds each step in real feedback instead of reasoning in "
            "isolation like plain chain-of-thought.")
_MISCONCEPTION = "ReAct is basically just chain-of-thought prompting."


def _react_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM concepts WHERE slug='react' OR name LIKE '%ReAct%' LIMIT 1").fetchone()
    if row:
        return row[0]
    row = conn.execute("SELECT concept_id FROM keypoints LIMIT 1").fetchone()  # any keypoint concept
    return row[0] if row else None


def _drive(answer: str, sid: str, max_turns: int) -> dict:
    conn = sqlite3.connect(":memory:", check_same_thread=False); init_db(conn)
    seed_demo_data(conn, _FIXTURE)
    ts = TutorSession(conn, sqlite3.connect(":memory:", check_same_thread=False), sid)
    rid = _react_id(conn)
    ts.start("agents", target_concept_ids=[rid] if rid else [], mastery_threshold=0.75)
    cur = ts.current()
    init_m = cur.get("mastery") or 0.0
    blooms, scores, miscs = [], [], []
    for _ in range(max_turns):
        if cur.get("done") or not cur.get("question"):
            break
        blooms.append(cur.get("bloom"))
        cur = ts.answer(answer)
        row = conn.execute("SELECT score, detected_misconception FROM quiz_attempts "
                           "WHERE session_id=? ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        if row:
            scores.append(row[0]); miscs.append(row[1])
    return {"init_m": init_m, "final_m": cur.get("mastery") or 0.0,
            "blooms": blooms, "scores": scores, "miscs": miscs}


def main() -> int:
    load_dotenv()
    gate = Gate("G-live-tutor")
    ok, why = live_enabled()
    if not ok:
        return gate.skip(why)

    correct = [_drive(_CORRECT, f"lt-c{i}", max_turns=3) for i in range(2)]
    misc = [_drive(_MISCONCEPTION, f"lt-m{i}", max_turns=1) for i in range(2)]

    # BUG 1 — mastery is persisted and MOVES on answers (was flat at the seed). It can legitimately
    # dip when a harder application-level answer is judged wrong, so assert it MOVED in every session
    # (the flat-bars regression) AND rose in at least one (correct answers push it up).
    c, n = k_of_n(correct, lambda r: abs(r["final_m"] - r["init_m"]) > 0.001)
    gate.hard("mastery moves off the seed (not flat)", c == n,
              f"{c}/{n}; " + ", ".join(f"{r['init_m']}->{r['final_m']}" for r in correct))
    c, n = k_of_n(correct, lambda r: r["final_m"] > r["init_m"])
    gate.hard("mastery rises in >=1 session", c >= 1, f"{c}/{n}")

    # N1 — a key-idea paraphrase is graded correct (the over-strict prompt rejected these)
    c, n = k_of_n(correct, lambda r: any(s == 1.0 for s in r["scores"]))
    gate.hard("a correct paraphrase is graded correct", c >= 1, f"{c}/{n}")

    # BUG 3 — quizzes escalate past recall
    c, n = k_of_n(correct, lambda r: any(b not in (None, "recall") for b in r["blooms"]))
    gate.hard("Bloom escalates past recall", c >= 1,
              f"{c}/{n}; blooms={[r['blooms'] for r in correct]}")

    # BUG 5 — a misconception is named on the keypoint path (was always None)
    c, n = k_of_n(misc, lambda r: any(m for m in r["miscs"]))
    gate.hard("misconception named on canonical wrong answer", c >= 1,
              f"{c}/{n}; named={[m for r in misc for m in r['miscs']]}")
    c, n = k_of_n(misc, lambda r: any(s == 0.0 for s in r["scores"]))
    gate.advisory("wrong answer graded 0", f"{c}/{n}")
    gate.advisory("advance-vs-concede honesty", "rule-computed; covered offline by test_keypoint_flow")
    return gate.finish()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
