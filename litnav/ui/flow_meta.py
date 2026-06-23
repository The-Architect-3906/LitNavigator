"""Node → research provenance mapping for the unified glass-box UI (OW-6 P6).

Each graph node is mapped to a dict with three keys:
  skill   — the high-level skill the node implements
  method  — the research method / algorithm used
  paper   — authoritative paper(s) behind the method

Drawn from docs/open-world-methods.md and docs/open-world-storyboard.md.
"""
from __future__ import annotations

NODE_META: dict[str, dict[str, str]] = {
    # ── Open-world build (DISCOVER → DIGEST) ─────────────────────────────────
    "discover": {
        "skill": "find-sources",
        "method": "intent classify → OpenAlex/Wikipedia/S2/arXiv search → embedding rerank + relevance gate",
        "paper": "BM25 (Robertson & Zaragoza); SPECTER-style rerank",
    },
    "digest": {
        "skill": "digest-corpus",
        "method": "concept/keypoint extraction → prerequisite edges (RefD-style + LLM judge) → cited graph",
        "paper": "RefD prerequisite relations (cf. Liang et al., 2015)",
    },
    # ── Goal / planning / orient ─────────────────────────────────────────────
    "goal_elicit": {
        "skill": "teach",
        "method": "goal→Bloom-ceiling (mastery / functional / survey)",
        "paper": "Bloom's taxonomy (Anderson & Krathwohl, revised)",
    },
    "planner": {
        "skill": "teach",
        "method": "prereq-ordered route plan",
        "paper": "RefD — Liang et al., EMNLP 2015",
    },
    "orient_tour": {
        "skill": "teach",
        "method": "roadmap walk (C4 progressive disclosure)",
        "paper": "Bloom's taxonomy; Mayer multimedia principles",
    },

    # ── Retrieval ────────────────────────────────────────────────────────────
    "retrieve": {
        "skill": "find-sources/digest",
        "method": "cited-evidence retrieval (chunk lookup by concept id)",
        "paper": "—",
    },

    # ── Keypoint path ────────────────────────────────────────────────────────
    "init_kp": {
        "skill": "teach",
        "method": "keypoint progress initialisation (LangGraph state)",
        "paper": "—",
    },
    "teach_kp": {
        "skill": "teach",
        "method": "Mayer multimedia · worked-example effect · strategy policy",
        "paper": "Mayer (multimedia learning); Sweller / Kalyuga (cognitive load + expertise-reversal)",
    },
    "assess_next": {
        "skill": "assess",
        "method": "Bloom-leveled QG · SAQUET distractor gate · IRT difficulty",
        "paper": "BloomLLM (EC-TEL 2024); SAQUET (AIED 2024); SMART (EMNLP 2025)",
    },
    "grade_kp": {
        "skill": "assess",
        "method": "BKT-lite mastery heuristic (never LLM self-judge)",
        "paper": "cf. Corbett & Anderson 1995 (BKT); arXiv:2603.02830 (KT beats LLM)",
    },
    "reteach_kp": {
        "skill": "teach",
        "method": "strategy-switch reteach (analogy→worked-example→contrast→direct)",
        "paper": "Kalyuga expertise-reversal effect; FSRS spaced repetition",
    },
    "advance_kp": {
        "skill": "assess",
        "method": "dual-threshold advance (mastery + confidence ≥ 2 observations)",
        "paper": "BKT (Corbett & Anderson 1995)",
    },

    # ── Lost / re-explain ────────────────────────────────────────────────────
    "handle_lost": {
        "skill": "teach",
        "method": "metacognitive re-explain / analogy strategy switch",
        "paper": "Kalyuga expertise-reversal effect",
    },

    # ── Prerequisite / replan ────────────────────────────────────────────────
    "diagnose": {
        "skill": "recommend",
        "method": "prerequisite-detour diagnosis",
        "paper": "RefD — Liang et al., EMNLP 2015",
    },
    "replan": {
        "skill": "recommend",
        "method": "prerequisite-detour re-route",
        "paper": "RefD — Liang et al., EMNLP 2015",
    },

    # ── Recommend next ───────────────────────────────────────────────────────
    "select_next": {
        "skill": "recommend-next",
        "method": "prereq filter + mastery-gain score (graph-derived, no LLM)",
        "paper": "—",
    },

    # ── Induction (off-graph) ────────────────────────────────────────────────
    "induce": {
        "skill": "digest",
        "method": "off-graph induction — derive prereq + misconception from evidence",
        "paper": "RefD-style — cf. Liang et al. 2015 (EMNLP); LLM graph extraction",
    },
    "induce_scaffold": {
        "skill": "digest",
        "method": "off-graph induction — derive prereq + misconception from evidence",
        "paper": "RefD-style — cf. Liang et al. 2015 (EMNLP); LLM graph extraction",
    },

    # ── Legacy path ──────────────────────────────────────────────────────────
    "teach": {
        "skill": "teach",
        "method": "Mayer multimedia · worked-example effect · strategy policy",
        "paper": "Mayer (multimedia learning); Sweller / Kalyuga (cognitive load)",
    },
    "check": {
        "skill": "assess",
        "method": "legacy Bloom-leveled quiz",
        "paper": "BloomLLM (EC-TEL 2024); SAQUET (AIED 2024)",
    },
    "grade": {
        "skill": "assess",
        "method": "BKT posterior mastery update (legacy path)",
        "paper": "Corbett & Anderson 1995 (BKT)",
    },
    "lecture": {
        "skill": "teach",
        "method": "no-quiz concept lecture (survey/functional ceiling)",
        "paper": "Bloom's taxonomy (Anderson & Krathwohl)",
    },
    "reteach": {
        "skill": "teach",
        "method": "strategy-switch reteach",
        "paper": "Kalyuga expertise-reversal effect",
    },
    "concede": {
        "skill": "teach",
        "method": "honest concession (tutor honesty principle)",
        "paper": "—",
    },
    "advance": {
        "skill": "assess",
        "method": "dual-threshold advance (mastery + confidence)",
        "paper": "BKT (Corbett & Anderson 1995)",
    },

    # ── Spaced-retrieval / probe ─────────────────────────────────────────────
    "review_probe": {
        "skill": "assess",
        "method": "spaced-retrieval probe (FSRS / Ebbinghaus forgetting curve)",
        "paper": "Nature Reviews Psychology 2022 (Kornell/Bjork); FSRS Ye et al.",
    },
    "grade_probe": {
        "skill": "assess",
        "method": "BKT posterior update on recall answer",
        "paper": "Corbett & Anderson 1995 (BKT)",
    },
}

_DEFAULT_META: dict[str, str] = {"skill": "—", "method": "—", "paper": "—"}


def meta_for(node: str) -> dict[str, str]:
    """Return the research provenance dict for *node*.

    Returns ``{"skill": "—", "method": "—", "paper": "—"}`` for any node
    not in NODE_META so callers never receive a KeyError.
    """
    return dict(NODE_META.get(node, _DEFAULT_META))


# ── Plain-language "why this next" chip copy ─────────────────────────────────
# Maps each route-decision token to a learner-facing sentence.
# Raw token stays behind the existing detail toggle; this copy goes in #why-human.
DECISION_SENTENCES: dict[str, str] = {
    "advance":   "You passed — moving on",
    "reteach":   "Let's try this a different way",
    "diagnose":  "Adding a prerequisite first",
    "replan":    "Adding a prerequisite first",
    "concede":   "Marking this not-yet and moving on",
    "bloom-up":  "Stepping up to apply-level",
    "lecture":   "No quiz needed — moving on",
}


def why_sentence(decision: str | None) -> str | None:
    """Map a raw decision token to a learner-facing sentence, or None if unknown."""
    if not decision:
        return None
    return DECISION_SENTENCES.get(decision.lower())


# ── Named mastery tiers ───────────────────────────────────────────────────────
# Matches Khan Academy tier naming; thresholds from the Direction B spec.
def mastery_tier(mastery: float) -> str:
    """Return a named tier label for a mastery score in [0, 1]."""
    if mastery >= 0.78:
        return "Mastered"
    if mastery >= 0.55:
        return "Solid"
    if mastery >= 0.30:
        return "Familiar"
    return "Seen"
