"""MCQ distractor generation, SAQUET-style flaw gating, and IRT difficulty estimation.

- make_distractors: overgenerate ~6 candidates via cheap LLM, filter the answer, deduplicate, cap to n.
- flaw_gate: SAQUET-style rejection of bad items (empty stem, <2 distractors, distractor==answer).
- estimate_difficulty: weaker/cheaper LLM simulator attempts the item; wrong -> harder (irt_b > 0),
  right -> easier (irt_b < 0); clamped to [-3, 3].
"""
from __future__ import annotations

import sqlite3

from litnav.llm import router


def make_distractors(
    question: str,
    answer_key: str,
    *,
    conn: sqlite3.Connection,
    session_id: str,
    n: int = 3,
    fallback: list[str] | None = None,
    budget: int | None = None,
) -> list[str]:
    """Return up to *n* plausible-but-wrong distractors for an MCQ item.

    Calls the cheap LLM tier to overgenerate ~6 candidates, then:
      1. Drops any candidate that case-insensitively equals *answer_key*.
      2. Deduplicates (preserving order).
      3. Returns the first *n*.

    Offline (provider=none): the client returns the fallback dict immediately, so the
    fallback list (minus the answer) is used instead.
    """
    fb_list: list[str] = list(fallback or [])
    fb_dict = {"distractors": fb_list}

    result = router.complete_json(
        f"Generate 6 plausible but WRONG distractors for the following quiz item.\n"
        f"Question: {question}\n"
        f"Correct answer: {answer_key}\n"
        f"Return JSON only: {{\"distractors\": [\"wrong1\", \"wrong2\", ...]}}",
        tier="cheap",
        stage="quizgen",
        fallback=fb_dict,
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    raw: list[str] = result.get("distractors") or fb_list
    answer_lower = answer_key.strip().lower()

    # Filter out the answer (case-insensitive), deduplicate, cap to n
    seen: set[str] = set()
    filtered: list[str] = []
    for d in raw:
        d_norm = d.strip()
        if d_norm.lower() == answer_lower:
            continue
        key = d_norm.lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(d_norm)
        if len(filtered) >= n:
            break

    return filtered


def flaw_gate(item: dict) -> tuple[bool, str]:
    """SAQUET-style structural flaw check.

    Returns (True, "ok") if the item passes all checks, or (False, reason) if it fails.

    Rejection criteria:
      - Empty question stem.
      - Fewer than 2 distinct distractors.
      - Any distractor case-insensitively equals answer_key.
    """
    question = (item.get("question") or "").strip()
    answer_key = (item.get("answer_key") or "").strip().lower()
    distractors: list[str] = item.get("distractors") or []

    if not question:
        return False, "empty stem"

    distinct = list({d.strip().lower() for d in distractors if d.strip()})
    if len(distinct) < 2:
        return False, f"fewer than 2 distinct distractors (got {len(distinct)})"

    for d in distinct:
        if d == answer_key:
            return False, f"distractor equals answer_key: {d!r}"

    return True, "ok"


def estimate_difficulty(
    item: dict,
    *,
    conn: sqlite3.Connection,
    session_id: str,
    budget: int | None = None,
) -> float:
    """Estimate IRT difficulty (irt_b) by simulating a struggling novice student.

    A cheap/weaker LLM tier is prompted to answer as a novice who struggles, then
    self-assesses correctness:
      - Weak student wrong  -> harder item  -> irt_b = +1.0
      - Weak student right  -> easier item  -> irt_b = -1.0

    Offline (provider=none): fallback dict triggers {"correct_self_assessment": True}
    from the fallback path, which is neutral -- but the offline fallback maps to 0.0
    (mid difficulty) so tests can verify the offline path stays within [-3, 3].

    Result is clamped to [-3.0, 3.0].
    """
    question = item.get("question", "")
    answer_key = item.get("answer_key", "")

    fallback_result = {"answer": "", "correct_self_assessment": True}

    result = router.complete_json(
        f"You are a struggling novice student. Answer this quiz question as if you do NOT "
        f"fully understand the topic. Then self-assess whether your answer is correct.\n"
        f"Question: {question}\n"
        f"Correct answer (for self-assessment only): {answer_key}\n"
        f"Return JSON only: "
        f'{{\"answer\": \"<your attempt>\", \"correct_self_assessment\": <true|false>}}',
        tier="cheap",
        stage="quizgen_irt",
        fallback=fallback_result,
        session_id=session_id,
        conn=conn,
        budget=budget,
    )

    # Offline path: fallback dict returns correct_self_assessment=True -> irt_b = -1.0.
    # But the spec says offline -> 0.0.  Detect offline: if result IS the fallback object
    # (same identity or empty answer with True assessment), return 0.0.
    got_correct = result.get("correct_self_assessment", True)
    got_answer = (result.get("answer") or "").strip()

    # Offline detection: provider=none makes the client return the fallback dict unchanged,
    # so the answer will be empty string ("").  When the LLM actually runs, the answer will
    # be a non-empty string.  We use the empty answer as the offline signal rather than the
    # env var so that monkeypatched tests (which replace complete_json directly) still work.
    if not got_answer:
        return 0.0

    # Map simulator outcome to irt_b
    if got_correct:
        raw_b = -1.0   # novice got it right -> easier
    else:
        raw_b = +1.0   # novice got it wrong -> harder

    return float(max(-3.0, min(3.0, raw_b)))
