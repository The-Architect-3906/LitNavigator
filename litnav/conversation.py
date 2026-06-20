"""Conversation dispatcher — classify each user message into one tutor action.

LLM-backed when a provider is set; deterministic fallback offline (= today's behavior:
quiz pending -> answer; else resolve_goal). The reply text is only ever a greeting, a short
guiding sentence, or an honest decline — never domain teaching (that goes through the
grounded teaching graph). Any LLM-proposed slug is validated against the known concept set.
"""
from __future__ import annotations

from litnav.goal import resolve_goal
from litnav.llm import client as llm_client

ACTIONS = {"chat", "set_goal", "answer", "aside", "out_of_scope"}

# Words a genuine side-question tends to open with (when it isn't already punctuated with '?').
# Yes/no starters ("is", "are", "does" …) and open question words.
_Q_LEADS = {"what", "why", "how", "when", "where", "who", "whom", "which", "whose",
            "is", "are", "was", "were", "does", "do", "did", "has", "have", "had",
            "will", "would", "should", "shall", "may", "might", "must",
            "can", "could", "wait", "explain", "hmm", "huh"}


def _looks_interrogative(message: str) -> bool:
    """A cheap, deterministic 'is this a question?' test for the aside guard below."""
    m = message.strip().lower()
    if not m:
        return False
    if m.endswith("?"):
        return True
    return m.split()[0].strip(",.!") in _Q_LEADS


def _fallback(message: str, concepts: list[dict], off: dict | None, quiz_pending: bool) -> dict:
    if quiz_pending:
        # If the message reads like a question rather than an answer attempt, treat it as an
        # aside even offline — the LLM dispatcher handles this more precisely when online.
        if _looks_interrogative(message):
            r = resolve_goal(message, concepts, off)
            slug = r["slug"] if r["kind"] in ("concept", "induce") else None
            return {"action": "aside", "slug": slug, "reply": ""}
        return {"action": "answer", "slug": None, "reply": ""}
    r = resolve_goal(message, concepts, off)
    if r["kind"] in ("concept", "induce"):
        return {"action": "set_goal", "slug": r["slug"], "reply": ""}
    names = ", ".join(c["name"] for c in concepts)
    return {"action": "out_of_scope", "slug": None,
            "reply": f"I can teach: {names}. What would you like to start with?"}


def dispatch(message: str, *, concepts: list[dict], off: dict | None,
             quiz_pending: bool, question: str | None = None) -> dict:
    """Return {action, slug, reply}. action ∈ ACTIONS; slug is a validated known slug or None."""
    fb = _fallback(message, concepts, off, quiz_pending)
    valid_slugs = {c["slug"] for c in concepts} | ({off["slug"]} if off else set())

    q = f'A quiz is pending: "{question}".' if quiz_pending else "No quiz is pending."
    prompt = (
        "You are the dispatcher for a tutor built ONLY from a fixed pack of LLM-agent papers.\n"
        f"Teachable concepts (slug: name): {[(c['slug'], c['name']) for c in concepts]}\n"
        f"Off-skeleton concept that can be INDUCED on request: {off['slug'] if off else None}\n"
        f"{q}\nUser message: {message!r}\n\n"
        "Choose ONE action:\n"
        "- answer: a quiz is pending and the message is an attempt to answer it. When a quiz is "
        "pending, DEFAULT to 'answer' — terse or partial replies still count as answer attempts.\n"
        "- aside: ONLY when a quiz is pending AND the message is clearly phrased as a QUESTION "
        "(not an answer attempt). Set slug ONLY to a listed concept whose name clearly matches "
        "the question; if it is about something NOT in the list (even if related), set slug to null.\n"
        "- set_goal: no quiz pending and the user wants to learn a listed/off-skeleton concept; set slug.\n"
        "- chat: a greeting, small talk, or a question about you/your capabilities.\n"
        "- out_of_scope: the user wants to learn something NOT in the concept list.\n"
        "HARD RULE: never put teaching or domain facts in 'reply'. 'reply' is only a greeting, "
        "a short guiding sentence, or an honest decline naming what you can teach. To teach, use set_goal.\n"
        'Respond as JSON: {"action": "<one of the five>", "slug": "<known slug or null>", "reply": "<short text or empty>"}'
    )
    res = llm_client.complete_json(prompt, fallback=fb)

    action = res.get("action")
    if action not in ACTIONS:
        return fb
    slug = res.get("slug")
    if slug not in valid_slugs:
        slug = None
    if action == "answer" and not quiz_pending:
        action = "chat"
    # Harm-asymmetry guard: mislabeling a real answer as an aside blocks the learner from ever
    # being graded/advancing, whereas mislabeling an aside as an answer just costs one stray
    # grade + reteach (self-correcting). So while a quiz is pending, only honor 'aside' when the
    # message actually reads as a question; otherwise treat it as an answer attempt. (Offline the
    # fallback already returns 'answer', so this only ever corrects a live-LLM misclassification.)
    if action == "aside" and quiz_pending and not _looks_interrogative(message):
        action, slug = "answer", None
    if action == "set_goal" and slug is None:
        return fb                      # can't teach an unknown target -> deterministic route
    reply = res.get("reply") or fb.get("reply") or ""
    return {"action": action, "slug": slug, "reply": reply}
