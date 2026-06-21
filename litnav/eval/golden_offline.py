"""Offline ($0, deterministic) per-stage golden scorers.

These need no LLM: they score the STRUCTURE/quality of extractor + quiz-gen output against a
labelled fixture. `objective_quality` checks a learning objective names a mechanism and isn't a
stub; `quiz_validity` checks a quiz is structurally answerable. Each returns the fraction of cases
classified correctly against the fixture's `good`/`valid` label (a classifier-accuracy metric).
"""
from __future__ import annotations

_MECH = (" how ", " why ", " so ", " to ", " by ", " because ", " enables ", " rather than ", " between ")


def _is_good_objective(text: str) -> bool:
    t = (text or "").strip()
    if len(t.split()) < 8:                          # placeholders like "explain ReAct" are short
        return False
    return any(m in f" {t.lower()} " for m in _MECH)  # names a mechanism / why-how


def objective_quality(cases: list[dict]) -> float:
    if not cases:
        return 1.0
    correct = sum(1 for c in cases if _is_good_objective(c["text"]) == c["good"])
    return round(correct / len(cases), 4)


def _is_valid_quiz(q: dict) -> bool:
    opts = q.get("options") or []
    return bool((q.get("question") or "").strip()) and len(opts) >= 3 and q.get("answer") in opts


def quiz_validity(cases: list[dict]) -> float:
    if not cases:
        return 1.0
    correct = sum(1 for c in cases if _is_valid_quiz(c["quiz"]) == c["valid"])
    return round(correct / len(cases), 4)
