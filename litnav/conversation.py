"""Conversation dispatcher — classify each user message into one tutor action.

LLM-backed when a provider is set; deterministic fallback offline (= today's behavior:
quiz pending -> answer; else resolve_goal). The reply text is only ever a greeting, a short
guiding sentence, or an honest decline — never domain teaching (that goes through the
grounded teaching graph). Any LLM-proposed slug is validated against the known concept set.
"""
from __future__ import annotations

from litnav.goal import resolve_goal
from litnav.llm import client as llm_client

ACTIONS = {"chat", "set_goal", "answer", "aside", "out_of_scope", "lost"}

# Words a genuine side-question tends to open with (when it isn't already punctuated with '?').
# Yes/no starters ("is", "are", "does" …) and open question words.
_Q_LEADS = {"what", "why", "how", "when", "where", "who", "whom", "which", "whose",
            "is", "are", "was", "were", "does", "do", "did", "has", "have", "had",
            "will", "would", "should", "shall", "may", "might", "must",
            "can", "could", "wait", "explain", "hmm", "huh"}

_RETEACH_CUES = (
    "i want to understand",
    "i want to learn",
    "help me understand",
    "teach me",
    "explain again",
    "can you explain",
    "could you explain",
    "i don't understand",
    "i dont understand",
)

_LOST_CUES = (
    "i'm lost",
    "im lost",
    "i am lost",
    "too hard",
    "too difficult",
    "back up",
    "back me up",
    "slow down",
    "give me the basics",
    "start from the beginning",
    "i'm confused",
    "im confused",
    "i am confused",
    "i don't get it",
    "i dont get it",
    "i have no idea",
    "what does that mean",
    "i need more context",
    # "I don't know" family — learner honesty should never be penalised as a wrong answer
    "i don't know",
    "i dont know",
    "don't know",
    "dont know",
    "idk",
)


def _looks_interrogative(message: str) -> bool:
    """A cheap, deterministic 'is this a question?' test for the aside guard below."""
    m = message.strip().lower()
    if not m:
        return False
    if m.endswith("?"):
        return True
    return m.split()[0].strip(",.!") in _Q_LEADS


def _looks_reteach_request(message: str) -> bool:
    """Detect meta-requests for explanation that should not be graded as answers."""
    m = " ".join(message.strip().lower().split())
    if not m:
        return False
    return any(m.startswith(prefix) for prefix in _RETEACH_CUES)


def _looks_lost(message: str) -> bool:
    """Detect 'I'm lost / too hard / back up' — learner needs simpler re-explanation."""
    m = " ".join(message.strip().lower().split())
    if not m:
        return False
    return any(cue in m for cue in _LOST_CUES)


_LEARN_CUES = ("teach", "learn", "understand", "study", "explain", "basics",
               "prereq", "prerequisite", "review", "brush up", "go over", "cover")


def _looks_learn_request(message: str) -> bool:
    """Distinguish 'I want to learn X' from a bare greeting. Used to decide whether an
    out-of-corpus message deserves an honest boundary bridge (naming X) vs the friendly
    'here's what I can teach' default — we don't want to slap a decline on a 'hello'."""
    m = " ".join(message.strip().lower().split())
    if not m:
        return False
    return any(cue in m for cue in _LEARN_CUES)


def _fallback(message: str, concepts: list[dict], off: dict | None, quiz_pending: bool) -> dict:
    # "lost / too hard / back up" is a first-class intent regardless of quiz state
    if _looks_lost(message):
        return {"action": "lost", "slug": None, "reply": ""}
    if quiz_pending:
        if _looks_reteach_request(message):
            r = resolve_goal(message, concepts, off)
            slug = r["slug"] if r["kind"] in ("concept", "induce") else None
            return {"action": "aside", "slug": slug, "reply": ""}
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
        "- aside: ONLY when a quiz is pending AND the message is either a clear QUESTION OR a "
        "meta-request to re-explain/understand the concept (for example: 'I want to understand "
        "ReAct', 'teach me again', 'I don't understand'). Set slug ONLY to a listed concept "
        "whose name clearly matches the message; if it is about something NOT in the list "
        "(even if related), set slug to null.\n"
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
    # Lost is a higher-priority override — never let the LLM downgrade it to "answer"
    if _looks_lost(message):
        action, slug = "lost", None
    elif quiz_pending and _looks_reteach_request(message):
        # A "teach me / I want to learn X" mid-quiz is a meta-request, never an answer to grade —
        # force it to aside even if the live LLM labeled it "answer". The aside handler re-resolves
        # the slug; an out-of-corpus topic (linear algebra) resolves to None → honest boundary reply.
        action = "aside"
    elif action == "aside" and quiz_pending and not (
        _looks_interrogative(message) or _looks_reteach_request(message)
    ):
        action, slug = "answer", None
    if action == "set_goal" and slug is None:
        return fb                      # can't teach an unknown target -> deterministic route
    reply = res.get("reply") or fb.get("reply") or ""
    return {"action": action, "slug": slug, "reply": reply}
