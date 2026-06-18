# LitNavigator — Two-Mode Agent UI Redesign

- **Date:** 2026-06-18
- **Status:** Design (approved in brainstorming; pending spec review)
- **Baseline:** commit `c6a14fa` (86 tests + G0–G3 green; live UI verified)

## 1. Context & Goal

The current `/tutor` UI is functional and judge-traceable, but it reads as crude: answers
submit via full-page GET reloads, styling is plain, and the live glass box was undermined by
an eager corpus-expansion side-effect (the evidence panel dumps the whole retrieved set,
including loosely auto-tagged expansion chunks). It does not *feel* like a real agent.

This redesign delivers **two switchable views of the same live session**:

- **Mode 1 — Chat:** a clean, modern chat with the teaching text revealed token-by-token
  (typewriter), no full-page reloads. The "consumer product" feel.
- **Mode 2 — Glass box / Agentic:** the agent's flow (plan → retrieve → teach → check →
  grade → route) lights up step-by-step as it executes, with cited evidence, learner model,
  decision rationale, and cost in front. The judge-facing "see it actually reason" view.
  This is the priority — it is where the agentic workflow and evidence become visible.

It also folds in the fix for the evidence-pollution regression introduced by the corpus
expansion.

## 2. Locked Decisions (from brainstorming)

1. **Two modes = two views of ONE live session**, toggled anytime via a top control (no
   reload, no re-run — the toggle just shows the other face of the same state).
2. **Real step streaming + typewriter teach.** The glass-box flow is driven by genuine
   per-node streaming (LangGraph `app.stream(stream_mode="updates")`) over SSE. The teaching
   text uses a client-side typewriter reveal of the text the teach node returned (visually
   like ChatGPT streaming; zero backend token-stream risk). True token-streaming out of a
   graph node is explicitly out of scope.
3. **Native `EventSource` + `fetch`, no front-end framework, no new dependency** (lighter
   than the htmx option floated earlier; keeps the "no SPA" stance).
4. **Server-rendered fallback preserved.** With JS off or SSE failed, the existing
   server-rendered page (from `current()`) still works — so the app degrades gracefully and
   stays testable offline.
5. **Evidence-pollution fix folded in** (see §4.3).

## 3. Architecture

Keep the backend (TutorSession over the LangGraph graph with `interrupt_after=["check"]`,
SQLite, `current()`, `build_trace` for the post-session panel). Add a streaming layer and
rewrite the session template.

- **Execution deferred to the stream:** `/tutor/start` creates the `TutorSession` and stores
  its initial parameters but does NOT run the graph. The first run happens inside the SSE
  stream so the first teaching turn animates live. A `started` flag guards against double-run.
- **No-JS fallback:** `GET /tutor/{sid}` renders the server page; if the session has not run
  yet it runs synchronously (`ensure_run()`) then renders `current()`. `GET
  /tutor/{sid}/answer` keeps working (sync inject + redirect).
- **SSE endpoint** streams node events for the JS path.
- **One template, two views, client-side toggle.** Both views live in the DOM; a segmented
  control toggles a class. One `EventSource` updates both.

## 4. Components

### 4.1 Backend streaming (`litnav/ui/interactive.py`)
- `prepare(topic, target_concept_ids, intent, pending_induction, mastery_threshold)` — stores
  the initial state without invoking. (`start()` is kept as `prepare()` + `ensure_run()` for
  the existing tests / fallback.)
- `ensure_run()` — if not `started`, invoke the graph to the interrupt synchronously; sets
  `started`.
- `stream_start()` / `stream_answer(text)` — generators that run the graph via
  `self.app.stream(input, self.config, stream_mode="updates")` and `yield` an event dict per
  node, then a terminal `state` + `teach` + `question` + `done`. `stream_answer` first
  `update_state({"user_answer": text, "pending_answers": []})`, then streams `None`.
- A `_event_for(node_name, update)` helper maps nodes → `{type:"step", node, label, detail}`.

**Event schema (JSON over SSE `data:` lines):**
| type | payload | drives |
|---|---|---|
| `step` | `{node, label, detail}` | glass-box flow lights up; chat "working…" line |
| `teach` | `{text, cited:[ids]}` | typewriter teach (chat bubble / glass-box card) |
| `question` | `{text}` | quiz + reveal answer input |
| `state` | `{route, route_version, learner, cited, decision, rationale, induced, cost}` | glass-box panels |
| `done` | `{done, mastery, confidence}` | completion + trace link |
| `error` | `{message}` | show a soft error; client falls back to reloading the server page |

### 4.2 SSE endpoint (`litnav/ui/server.py`)
- `GET /tutor/{sid}/events?answer=...` → `text/event-stream`. No `answer` and not `started`
  → iterate `stream_start()`; otherwise iterate `stream_answer(answer)`. Each yielded event
  → `f"data: {json.dumps(event)}\n\n"`. Wrap the iteration in try/except → emit an `error`
  event and stop.
- `/tutor/start?goal=…&intent=…` → create session via `prepare()` (no run) → redirect to
  `/tutor/{sid}`. Keep the goal/intent/unknown resolution logic unchanged.
- `/tutor/{sid}` → render the two-view shell plus the latest `current()` snapshot. With JS,
  the client opens the SSE stream which runs/animates the turn. The shell carries a
  `<noscript>` fallback link to `/tutor/{sid}?run=1`, which calls `ts.ensure_run()` (sync) and
  renders the full server page — so the app works without JS too.
- **`started` semantics for the stream:** `stream_start()` animates per-node only on the
  genuinely-first run. If the session was already run (e.g. via the no-JS `?run=1` path), the
  events endpoint emits the terminal `state`/`teach`/`question` directly instead of
  re-animating. Per-node animation always happens on each `answer` turn. (Exact triggering
  is finalized in the plan — see §8.)

### 4.3 Evidence-pollution fix
- `litnav/nodes/retrieve.py`: order retrieved chunks so **curated chunks (`id` starts with
  `c_`) come before expansion chunks (`cx_`)**. Teach/reteach pick `evidence[idx]`, so demo
  concepts stay grounded in curated text; expansion chunks remain as lower-priority evidence.
- `current()` adds `cited` = the actually-cited chunks (`current_cited_chunks`) resolved to
  `{chunk_id, text, paper_id}`. The glass box shows `cited` only — not the whole retrieved
  set.

### 4.4 Frontend (`litnav/ui/templates/agent.html`, rewritten; `agent_home.html` unchanged)
- Top bar: brand · goal/mode · segmented toggle `[Chat | Glass box]` · corpus "N papers".
- **Mode 1 (Chat):** chat thread (user goal bubble, agent teach bubble with typewriter, quiz
  bubble), bottom answer input (submits by opening `/tutor/{sid}/events?answer=…`), a "●
  agent working" indicator during streaming. Glass box hidden.
- **Mode 2 (Glass box):** the agent-flow timeline (steps ✓done/▶active/○pending with a
  one-line result each), evidence card (cited-only), learner mastery/confidence bars + held
  misconceptions, induced provenance + `confidence_basis` when present, cost panel; a slim
  conversation strip with the answer input. Flow + evidence are the focus.
- One `EventSource` per run; JS dispatches events to update both views. Toggle = client-side
  class swap (no reload/re-run). Responsive: glass box stacks under chat on narrow screens;
  no horizontal overflow.

## 5. Error Handling
- SSE generator wraps the graph stream in try/except → `error` event, then closes.
- LLM failures inside nodes already fall back to deterministic output (existing) — the stream
  still completes with valid `teach`/`state`.
- Client `EventSource.onerror` → reload `/tutor/{sid}` (server-rendered fallback).
- JS disabled → server-rendered page via `ensure_run()`.

## 6. Testing
- **Python-level stream tests** (offline, provider=none): iterate `stream_start()` and
  `stream_answer()`; assert the event sequence contains ≥1 `step`, a `teach`, a `question`,
  a final `state`/`done`; and that an answer drives a route decision.
- **retrieve curated-first** unit test: a concept with both `c_` and `cx_` chunks returns the
  `c_` chunk at index 0.
- **current() cited** test: `cited` equals the chunks teach actually cited (subset of
  retrieved), not the whole set.
- **SSE endpoint** test (TestClient streaming): `GET /tutor/{sid}/events` returns
  `text/event-stream` and at least one `data:` line.
- **Keep existing route tests green** (the server-rendered fallback path): `/tutor`,
  `/tutor/start`, `/tutor/{sid}`, intent mode.
- Client JS (typewriter, toggle, live animation) is verified manually via the preview
  (screenshots), not unit-tested.
- Full suite + G0–G3 stay green offline.

## 7. Out of Scope (YAGNI)
True token-streaming out of graph nodes; SPA framework; auth/multi-user; persistence across
restart; mobile-native. The corpus stays at the current 25-paper fixture.

## 8. Deferred to the implementation plan
- Exact SSE generator/event code and the node→label map.
- Exact `agent.html` markup/CSS and the JS dispatch/typewriter.
- Whether `/tutor/{sid}` runs `ensure_run()` eagerly (simplest, always-complete page) vs a
  `?run=1` path — pick the eager option unless it double-animates; resolve in the plan.
