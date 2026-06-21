# LitNavigator — Conversational Agent Layer

- **Date:** 2026-06-18
- **Status:** Design (approved direction in brainstorming; pending spec review)
- **Baseline:** commit `6e2639b` (91 tests + G0–G3 green; two-mode UI live)

## 1. Context & Goal

Today the `/tutor` front door is a **classifier** (`resolve_goal` → concept / induce /
unknown). Non-goal input — a greeting, chit-chat, a vague or out-of-scope request — falls to
`unknown` and gets a canned decline. Typing "你好" returns the rigid "not in this paper
corpus" template. That does not feel like a real LLM agent.

**Goal:** make `/tutor` a **full conversational agent** — you can say anything each turn and
the agent decides how to respond (chat / clarify / teach / handle a mid-quiz aside) — while
**teaching stays grounded in the corpus and never hallucinates**. The agent converses
freely; it only *teaches* from cited evidence.

## 2. Locked Decisions (brainstorming)

1. **Full conversational agent**: every turn is free text; an LLM dispatcher decides the
   action. (Not just a conversational front door.)
2. **Mid-quiz smart distinction**: when a quiz is pending, the dispatcher decides whether the
   message is an **answer** (→ grade) or an **aside/command** (→ answer the aside from
   evidence if in-corpus, then **re-pose the same quiz**).
3. **Teaching graph is unchanged.** The conversation layer sits in front of the proven
   `TutorSession` graph and decides *when* to invoke it; it never modifies it.
4. **Grounding is preserved.** Only the teaching graph emits domain content (cited). Chat
   replies are about the tutor / guidance and **never assert unsourced domain facts**.
5. **Offline fallback = today's behavior.** With `provider=none` the dispatcher degrades to
   the current deterministic rule (quiz pending → treat as answer; else `resolve_goal`), so
   all gates + tests stay green with no network.

## 3. Architecture

A new **dispatcher** classifies each user message; an **AgentSession** wraps the
conversation transcript plus a lazily-created `TutorSession` (the teaching engine).

```
user message ──▶ dispatch(message, ctx) ──▶ action + reply + slug
                      │
   ┌──────────────────┼─────────────────────────────────────────────┐
   ▼                  ▼                ▼              ▼               ▼
 chat            set_goal           answer          aside        out_of_scope
 (free reply)  (start/redirect    (TutorSession   (brief grounded (conversational
               teaching, grounded) .answer/grade) answer + re-pose) decline + scope)
```

- **`dispatch(message, ctx)`** — `litnav/conversation.py`. Uses `complete_json` with a
  deterministic fallback. `ctx` = concept list, off-skeleton, quiz-pending flag + the pending
  question, current concept, intent. Returns
  `{action, reply, slug}` where `action ∈ {chat, set_goal, answer, aside, out_of_scope}`,
  `reply` is natural text (for chat / out_of_scope / the lead-in of an aside), `slug` is the
  target concept for set_goal/aside (validated against known slugs; null otherwise).
- **`reply` generation** — for `chat`/`out_of_scope`, a `complete_text` call with a scoped
  system prompt: "You are a tutor built from N LLM-agent papers. Greet/guide; tell the
  learner what you can teach (the concept list); ask what they want to learn. Do NOT teach or
  assert domain facts — to teach, the system routes to grounded teaching." Deterministic
  fallback strings offline.
- **`AgentSession`** — `litnav/ui/interactive.py` (new class, alongside `TutorSession`).
  Holds the chat transcript and an optional `TutorSession` (created when the first concept is
  chosen). `handle(message)` runs the dispatcher and yields UI events (below). A session can
  exist in "conversing, no teaching yet" state (e.g. opened with a greeting).
- **Teaching** remains entirely inside `TutorSession` (graph + interrupt/resume), unchanged.

### 3.1 Action handling
- `chat` → emit a `reply` event (assistant chat bubble). No teaching.
- `set_goal` → (create or re-target the `TutorSession` to `slug`; if off-skeleton, induce)
  then stream the teaching turn (existing per-node `stream` events).
- `answer` (only when a quiz is pending) → `TutorSession.stream_answer(message)` (existing).
- `aside` (quiz pending, message is a side question) → if `slug` is in-corpus, produce a
  **brief grounded answer** (retrieve that concept's top chunk + a short `complete_text`
  grounded on it, cited), emit it as a `reply`, then re-emit the pending `question` event so
  the learner can still answer. If not in-corpus → `out_of_scope` reply, then re-pose.
- `out_of_scope` → emit a `reply` that declines conversationally and lists what can be taught.

### 3.2 Anti-hallucination boundary (hard rule)
- The dispatcher prompt explicitly forbids putting domain teaching in `reply`; teaching only
  happens via the grounded graph. `reply` is limited to: greetings, capability/scope
  explanation, guidance/clarifying questions, and honest declines.
- `aside` answers are produced only from retrieved corpus chunks (cited), never free-form.
- Slugs from the LLM are validated against the known concept set (as `resolve_goal` already
  does) before any teaching action.

## 4. Frontend

Chat mode becomes a real multi-turn conversation: the input stays available every turn;
each user message posts to the streaming endpoint; the agent's reply / teaching / quiz render
as chat bubbles (typewriter for assistant text). The Glass box gains a first step showing the
**dispatch decision** ("understood as: chat / teaching ReAct / grading / aside …"), making
the agentic routing visible. Existing step/teach/question/state/done events are reused; a new
`reply` event carries conversational text.

## 5. Events (additions)
| event | payload | drives |
|---|---|---|
| `reply` (new) | `{text}` | assistant chat bubble (typewriter); used by chat / out_of_scope / aside lead-in |
| `dispatch` (new) | `{action, label}` | a glass-box step: "understood as <action>" |
| `step`/`teach`/`question`/`state`/`done` | (unchanged) | teaching turns |

## 6. Error handling & offline
- Dispatcher/`complete_json` failure or `provider=none` → deterministic fallback: quiz
  pending → `answer`; else `resolve_goal` (concept/induce/unknown→out_of_scope). So offline
  behavior equals today (gates/tests green), just without the conversational flourish.
- Any LLM error inside teaching already falls back to deterministic output.

## 7. Testing
- **dispatch (offline)**: quiz-pending + arbitrary text → `answer`; no quiz + "I want ReAct"
  → `set_goal`/react; greeting/garbage with no quiz → `out_of_scope` (fallback) — i.e. parity
  with today offline.
- **dispatch (LLM mocked)**: monkeypatch `complete_json` to return `chat` / `aside` and assert
  AgentSession emits a `reply` (and, for aside, re-emits the `question`).
- **aside re-poses the quiz**: after an aside turn, the pending question is shown again and the
  learner can still answer correctly → grade succeeds.
- **grounding**: an `aside`/`chat` reply never bypasses retrieval to assert teaching content
  (assert aside text is built from a real chunk; assert chat path makes no teaching claim —
  structurally, chat never calls the teacher).
- Keep all existing route/interactive tests green (offline path unchanged).
- Full suite + G0–G3 green offline.

## 8. Out of scope (YAGNI)
Cross-session memory; arbitrary-corpus ingestion; tools beyond teaching; voice; true
token-streaming of teach text (typewriter stays). Corpus stays at 25 papers.

## 9. Deferred to the implementation plan
- The exact dispatcher prompt + the JSON action schema wording.
- Whether `AgentSession` is a new class or `TutorSession` grows a conversational entry (lean:
  new `AgentSession` wrapping `TutorSession`, to keep the teaching engine untouched).
- Exact `reply`/`dispatch` event wiring + the multi-turn chat front-end changes.
- The brief-grounded-aside implementation (reuse `retrieve` + `complete_text`).
