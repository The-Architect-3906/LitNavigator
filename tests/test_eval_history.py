from litnav.eval.scorecard import Scorecard
from litnav.eval.history import append, load, curve


def _sc(mr):
    return Scorecard(
        "c", 0.0, {"mastered_rate": mr, "avg_turns": 9, "usd": 0.01},
        {"grading_acc": 0.8, "prereq_survival": 0.5, "objective_quality": 0.8,
         "quiz_validity": 0.9, "discover_relevance": 0.7},
        {"avg_mastery_delta": 0.3}, {"passed": 275, "total": 275},
    )


def test_append_and_load_roundtrip(tmp_path):
    p = tmp_path / "h.jsonl"
    append(str(p), _sc(0.5))
    append(str(p), _sc(0.7))
    rows = load(str(p))
    assert len(rows) == 2 and rows[1]["e2e"]["mastered_rate"] == 0.7


def test_curve_is_monotone_when_improving(tmp_path):
    p = tmp_path / "h.jsonl"
    append(str(p), _sc(0.5))
    append(str(p), _sc(0.7))
    c = curve(str(p))
    assert c[1] > c[0]


def test_load_missing_file_is_empty(tmp_path):
    assert load(str(tmp_path / "nope.jsonl")) == []
