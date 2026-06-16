from __future__ import annotations

import re

_NEGATION_TOKENS = {"no", "not", "never", "isnt", "isn't", "arent", "aren't"}


def _normalize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def grade_answer(user_answer: str, answer_key: str) -> tuple[float, str]:
    answer_tokens = _normalize(user_answer)
    key_tokens = _normalize(answer_key)
    correct = False
    if answer_tokens and key_tokens and len(answer_tokens) >= len(key_tokens):
        window = len(key_tokens)
        for start in range(len(answer_tokens) - window + 1):
            if answer_tokens[start : start + window] != key_tokens:
                continue
            prefix = answer_tokens[max(0, start - 3) : start]
            if any(t in _NEGATION_TOKENS for t in prefix):
                continue
            correct = True
            break
    score = 1.0 if correct else 0.0
    feedback = "Correct." if correct else f"Expected something like: {answer_key}"
    return score, feedback
