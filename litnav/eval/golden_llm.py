"""LLM-dependent per-stage golden scorers (small, cheap-tier live; offline-testable via stubs).

Each takes an injected callable so tests run offline/$0 with a deterministic stub, while production
passes a thin wrapper over the real grader / prereq judge. Both return classifier accuracy against
the fixture labels (balanced positive/negative cases).
"""
from __future__ import annotations


def grading_accuracy(cases: list[dict], *, grade_fn) -> float:
    """grade_fn(question, answer_key, learner_answer) -> bool (is the answer correct?)."""
    if not cases:
        return 1.0
    ok = sum(
        1 for c in cases
        if bool(grade_fn(c["question"], c["answer_key"], c["learner_answer"])) == c["correct"]
    )
    return round(ok / len(cases), 4)


def prereq_survival(cases: list[dict], *, judge_fn) -> float:
    """judge_fn(prereq, target) -> bool (is prereq a genuine prerequisite of target?).

    Balanced accuracy: rewards keeping TRUE prereq edges and rejecting FALSE ones.
    """
    if not cases:
        return 1.0
    ok = sum(1 for c in cases if bool(judge_fn(c["prereq"], c["target"])) == c["is_prereq"])
    return round(ok / len(cases), 4)
