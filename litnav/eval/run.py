"""Assemble a Scorecard from the probe + golden sets (+ offline suite) and append eval-history.

`build_scorecard` is offline-deterministic by default (the grader/judge degrade to safe fallbacks
when provider=none), so it is testable and cheap per iteration; under a live provider the same
grader/judge call the real model. CLI: `python -m litnav.eval.run [--label X] [--no-suite]`.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from litnav.eval.scorecard import Scorecard, weighted_headline
from litnav.eval.history import append
from litnav.eval.mastery_probe import run_probe
from litnav.eval.golden_offline import objective_quality, quiz_validity
from litnav.eval.golden_llm import grading_accuracy, prereq_survival

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _ROOT / "data" / "eval" / "golden"
_HISTORY = _ROOT / "docs" / "eval" / "eval-history.jsonl"


def _live_grade(question: str, answer_key: str, learner_answer: str) -> bool:
    """Offline-safe grader: real key-idea LLM grade under a live provider; substring fallback offline."""
    from litnav.llm import router
    c = sqlite3.connect(":memory:")
    from litnav.storage.schema import init_db
    init_db(c)
    verdict = router.complete_json(
        "Judge ONLY whether the learner's answer conveys the expected key idea (accept paraphrases). "
        "Return JSON only.\n"
        f"Question: {question}\nExpected key idea: {answer_key}\nLearner's answer: {learner_answer!r}\n"
        '{"correct": true or false}',
        tier="cheap", stage="eval_grade",
        fallback={"correct": answer_key.lower() in (learner_answer or "").lower()},
        session_id="eval", conn=c,
    )
    return bool(verdict.get("correct"))


def _live_judge(prereq: str, target: str) -> bool:
    """Offline-safe prereq judge: real LLM under a live provider; keep-by-default fallback offline."""
    from litnav.llm import router
    c = sqlite3.connect(":memory:")
    from litnav.storage.schema import init_db
    init_db(c)
    verdict = router.complete_json(
        "Is the first concept a genuine prerequisite for understanding the second? Return JSON only.\n"
        f"First: {prereq}\nSecond: {target}\n"
        '{"is_prereq": true or false}',
        tier="frontier", stage="eval_prereq",
        fallback={"is_prereq": True},
        session_id="eval", conn=c,
    )
    return bool(verdict.get("is_prereq"))


def _load(name: str) -> list[dict]:
    return json.loads((_GOLDEN / name).read_text())


def _run_offline_suite() -> dict:
    import re
    import subprocess
    proc = subprocess.run([".venv/bin/python", "-m", "pytest", "-q", "--no-header", "--color=no"],
                          cwd=str(_ROOT), capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    return {"passed": passed, "total": passed + failed}


def build_scorecard(*, grade_fn=_live_grade, judge_fn=_live_judge,
                    run_suite: bool = False, commit: str = "HEAD", ts: float = 0.0) -> Scorecard:
    probe = run_probe()
    golden = {
        "grading_acc": grading_accuracy(_load("grading.json"), grade_fn=grade_fn),
        "prereq_survival": prereq_survival(_load("prereq_pairs.json"), judge_fn=judge_fn),
        "objective_quality": objective_quality(_load("objectives.json")),
        "quiz_validity": quiz_validity(_load("quizzes.json")),
    }
    suite = _run_offline_suite() if run_suite else {"passed": 0, "total": 0}
    return Scorecard(
        commit=commit, ts=ts,
        e2e={"mastered_rate": probe["mastered_rate"], "avg_turns": probe["avg_turns"], "usd": probe["usd"]},
        golden=golden,
        learning_gain={"avg_mastery_delta": probe["avg_mastery_delta"]},
        offline_suite=suite,
        notes=f"reteach_recovery={probe['reteach_recovery']}",
    )


def main() -> None:
    import argparse
    import subprocess
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--no-suite", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="load .env so grading/prereq golden run against the real provider")
    args = ap.parse_args()

    if args.live:
        from litnav.config import load_dotenv
        load_dotenv()  # project loader: picks up LITNAV_LLM_* / OPENAI_API_KEY from .env

    commit = (subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(_ROOT),
                             capture_output=True, text=True).stdout.strip() or "HEAD")
    sc = build_scorecard(run_suite=not args.no_suite, commit=commit, ts=time.time())
    if args.label:
        sc.notes = f"{sc.notes} {args.label}".strip()
    _HISTORY.parent.mkdir(parents=True, exist_ok=True)
    append(str(_HISTORY), sc)
    print(f"headline={weighted_headline(sc):.4f}  e2e={sc.e2e}  golden={sc.golden}  "
          f"learning_gain={sc.learning_gain}  suite={sc.offline_suite}  notes={sc.notes}")


if __name__ == "__main__":
    main()
