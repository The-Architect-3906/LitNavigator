import json
from pathlib import Path

from litnav.eval.golden_offline import objective_quality, quiz_validity

_GOLDEN = Path(__file__).resolve().parent.parent / "data" / "eval" / "golden"


def test_objective_quality_separates_good_from_placeholder():
    cases = [
        {"text": "Explain how ReAct interleaves reasoning and actions so the agent grounds decisions in observations.", "good": True},
        {"text": "explain ReAct", "good": False},
    ]
    assert objective_quality(cases) == 1.0  # both classified correctly


def test_quiz_validity_flags_malformed():
    cases = [
        {"quiz": {"question": "Q?", "options": ["a", "b", "c"], "answer": "a"}, "valid": True},
        {"quiz": {"question": "", "options": ["a"], "answer": "z"}, "valid": False},
    ]
    assert quiz_validity(cases) == 1.0


def test_objective_fixture_scores_high():
    cases = json.loads((_GOLDEN / "objectives.json").read_text())
    assert len(cases) >= 15 and objective_quality(cases) >= 0.85


def test_quiz_fixture_scores_high():
    cases = json.loads((_GOLDEN / "quizzes.json").read_text())
    assert len(cases) >= 15 and quiz_validity(cases) >= 0.85
