"""G-teach-assess (offline determinism/schema UNIT gate) — NOT capability evidence.
Validates deterministic TEACH/ASSESS logic: goal heuristic, Bloom ceiling, distractor flaw gate,
weaker-simulator difficulty bounds (offline), FSRS interval cadence + fast-forward, strategy policy,
retention-log write. The CAPABILITY is proven by verify_teach_assess_live."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.state import bloom_ceiling_for, BLOOM_LADDER
from litnav.nodes import goal_elicit
from litnav.assess import quizgen, spacing, strategy


def main() -> int:
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")

    # Goal heuristic: "quick overview" -> survey, "need to build X" -> functional
    assert goal_elicit.classify_goal("give me a quick overview", conn=c, session_id="s") == "survey"
    assert goal_elicit.classify_goal("I need to build X", conn=c, session_id="s") == "functional"

    # Bloom ceiling returns a valid level from BLOOM_LADDER
    assert bloom_ceiling_for("survey") in BLOOM_LADDER
    assert bloom_ceiling_for("survey") == "comprehension"
    assert bloom_ceiling_for("functional") == "application"
    assert bloom_ceiling_for("mastery") == "application"
    print("G-teach-assess PASS: goal heuristic + Bloom ceiling")

    # SAQUET flaw gate: distractor == answer_key -> fail; distinct distractors != answer -> pass
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["x", "b"]})[0] is False
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["a", "b", "c"]})[0] is True
    # Fewer than 2 distinct distractors -> fail
    assert quizgen.flaw_gate({"question": "q", "answer_key": "x", "distractors": ["a"]})[0] is False
    # Empty stem -> fail
    assert quizgen.flaw_gate({"question": "", "answer_key": "x", "distractors": ["a", "b"]})[0] is False
    print("G-teach-assess PASS: SAQUET flaw gate")

    # FSRS cadence: higher mastery -> longer interval (including fast-forward at >= 0.95)
    # interval_days(0.80) = 1/(1-0.80) = 5.0
    # interval_days(0.95) = 1/(1-0.95) * 2 = 40.0 (fast-forward)
    assert spacing.interval_days(0.95) > spacing.interval_days(0.80)
    # Offline estimate_difficulty returns 0.0 (within bounds [-3, 3])
    item = {"question": "What does X do?", "answer_key": "Y"}
    irt_b = quizgen.estimate_difficulty(item, conn=c, session_id="s")
    assert -3.0 <= irt_b <= 3.0, f"irt_b out of bounds: {irt_b}"
    assert irt_b == 0.0, f"offline estimate_difficulty should return 0.0, got {irt_b}"
    # Retention log write
    spacing.log_retention(c, "s", 1, predicted=0.82, actual=0.6, probed_at="2026-06-20T00:00:00")
    assert c.execute("SELECT COUNT(*) FROM retention_log WHERE session_id='s'").fetchone()[0] == 1
    print("G-teach-assess PASS: FSRS cadence + retention log")

    # Strategy policy (purely deterministic, no LLM)
    assert strategy.choose_strategy("survey", "novice", 0.2) == "overview"
    assert strategy.choose_strategy("mastery", "novice", 0.2) in {"worked_example", "direct"}
    assert strategy.choose_strategy("mastery", "novice", 0.2) == "worked_example"   # 0.2 < 0.35
    assert strategy.choose_strategy("mastery", "novice", 0.5) == "analogy"          # 0.35 <= 0.5 < 0.7
    assert strategy.choose_strategy("mastery", "expert", 0.5) == "concise"          # expert wins
    print("G-teach-assess PASS: strategy policy")

    print("G-teach-assess: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
