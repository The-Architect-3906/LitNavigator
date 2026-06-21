"""Detect the language a learner wants output in, from their goal text."""
from __future__ import annotations
import os, re, sqlite3
from litnav.llm import router


def _heuristic(text: str) -> str:
    if re.search(r"[一-鿿]", text): return "Chinese"
    if re.search(r"[぀-ヿ]", text): return "Japanese"
    if re.search(r"[가-힯]", text): return "Korean"
    if re.search(r"[Ѐ-ӿ]", text): return "Russian"
    if re.search(r"[؀-ۿ]", text): return "Arabic"
    return "English"   # Latin-script default; refined by the LLM when live


def detect_language(text: str, *, conn: sqlite3.Connection | None = None,
                    session_id: str | None = None, budget: int | None = None) -> str:
    """Return an English language NAME (e.g. 'Chinese','Spanish','English'). Offline = heuristic
    (CJK/Cyrillic/Arabic by script; else English). Live = cheap LLM (separates Latin langs like
    Spanish/French/English that the heuristic cannot)."""
    fb = _heuristic(text)
    if os.environ.get("LITNAV_LLM_PROVIDER", "").lower() in ("none", "offline"):
        return fb
    res = router.complete_json(
        f"What language is this learning goal written in? Reply with the English name of the language only.\n"
        f"Goal: {text}\n" 'Respond JSON only: {"language": "<English name>"}',
        tier="cheap", stage="discover", fallback={"language": fb},
        session_id=session_id, conn=conn, budget=budget)
    lang = res.get("language") if isinstance(res, dict) else None
    return lang.strip() if isinstance(lang, str) and lang.strip() else fb
