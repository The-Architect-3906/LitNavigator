"""G-teach-assess-live (LIVE): prove TEACH/ASSESS works on a real provider. Skips at provider=none."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.nodes import goal_elicit, grade_kp
from litnav.assess import quizgen
from litnav.llm import client as llm_client


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-teach-assess-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")

    # 1) goal elicitation runs live + is metered
    gt = goal_elicit.classify_goal("I want to deeply master multi-agent reasoning", conn=c, session_id="s")
    assert llm_client.was_live(), "FAIL: goal elicit not live"
    assert gt in {"mastery", "functional", "survey"}
    print(f"G-teach-assess-live PASS: goal classified live = {gt!r}")

    # 2) distractors generate live and pass the flaw gate
    ds = quizgen.make_distractors("What does ReAct interleave?", "reasoning and acting",
                                  conn=c, session_id="s", n=3, fallback=[])
    ok, why = quizgen.flaw_gate({"question": "q", "answer_key": "reasoning and acting", "distractors": ds})
    assert ds and ok, f"FAIL: distractors flawed ({why}): {ds}"
    print(f"G-teach-assess-live PASS: {len(ds)} distractors pass the flaw gate")

    # 3) a grade runs live + is metered (stage=grade)
    # Build a minimal state dict matching the ConceptProgress + NavState shape grade_kp_node expects
    state = {
        "session_id": "s",
        "concept_progress": {
            "concept_id": 1,
            "phase": "assessing",
            "keypoints": ["kp1"],
            "taught_idx": 1,
            "current_keypoint_id": "kp1",
            "current_bloom": "recall",
            "keypoint_state": {
                "kp1": {
                    "keypoint_id": "kp1",
                    "mastery": 0.4,
                    "correct_obs": 0,
                    "last_result": None,
                    "reteach_count": 0,
                    "strategies_used": [],
                }
            },
            "misconceptions": {},
        },
        "current_quiz_item": {
            "id": 1,
            "question": "What does ReAct interleave?",
            "answer_key": "reasoning and acting",
            "rubric": "must mention reasoning + acting",
            "expected_keypoints": "reasoning, acting",
            "evidence_chunk_id": None,
            "targets_misconception": None,
        },
        "pending_answers": ["reasoning traces and actions"],
        "user_answer": "reasoning traces and actions",
        "current_cited_chunks": [],
        "history": [],
    }
    grade_kp.grade_kp_node(state, c)
    spend = cost_repo.session_spend(c, "s")
    assert spend["tokens"] > 0, "FAIL: no live spend recorded"
    graded = c.execute("SELECT COUNT(*) FROM cost_ledger WHERE stage IN ('grade','grade_escalate')").fetchone()[0]
    assert graded >= 1, "FAIL: grade not metered"
    print(f"G-teach-assess-live PASS: grade metered; total spend usd={spend['usd']}")
    print("--- COST ledger ---")
    for row in c.execute("SELECT stage,tier,model,SUM(total_tokens),ROUND(SUM(usd),6),COUNT(*) "
                         "FROM cost_ledger GROUP BY stage,tier,model ORDER BY stage"):
        print("  ", tuple(row))
    print("G-teach-assess-live: ALL PASS"); return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
