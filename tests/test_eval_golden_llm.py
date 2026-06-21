import json
from pathlib import Path

from litnav.eval.golden_llm import grading_accuracy, prereq_survival

_GOLDEN = Path(__file__).resolve().parent.parent / "data" / "eval" / "golden"


def test_grading_accuracy_with_perfect_stub():
    cases = [{"question": "q", "answer_key": "k", "learner_answer": "k paraphrase", "correct": True}]
    acc = grading_accuracy(cases, grade_fn=lambda q, key, ans: True)  # stub says correct
    assert acc == 1.0


def test_prereq_survival_counts_kept():
    cases = [{"prereq": "a", "target": "b", "is_prereq": True}]
    surv = prereq_survival(cases, judge_fn=lambda pr, tg: True)  # stub keeps it
    assert surv == 1.0


def test_grading_fixture_oracle_stub_is_perfect():
    # An oracle stub that returns the labelled answer must score 1.0 — proves fixture shape.
    cases = json.loads((_GOLDEN / "grading.json").read_text())
    assert len(cases) >= 15
    by_text = {(c["question"], c["learner_answer"]): c["correct"] for c in cases}
    acc = grading_accuracy(cases, grade_fn=lambda q, key, ans: by_text[(q, ans)])
    assert acc == 1.0


def test_prereq_fixture_oracle_stub_is_perfect():
    cases = json.loads((_GOLDEN / "prereq_pairs.json").read_text())
    assert len(cases) >= 12
    by_pair = {(c["prereq"], c["target"]): c["is_prereq"] for c in cases}
    surv = prereq_survival(cases, judge_fn=lambda pr, tg: by_pair[(pr, tg)])
    assert surv == 1.0
