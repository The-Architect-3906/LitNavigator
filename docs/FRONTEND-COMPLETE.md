# Frontend — Complete Reference

*The unified glass-box + learner web UI: one page that teaches a real learner **and** exposes the full
agent reasoning (skill · method · paper · live scores). This is the complete frontend reference — what
ships, how it's built, and every module, route, event, and token.* Backend it talks to:
[BACKEND-COMPLETE](BACKEND-COMPLETE.md). Remaining work: [FRONTEND-ROADMAP](FRONTEND-ROADMAP.md).

**Run it:** `python -m litnav.ui.server` → http://127.0.0.1:8000/tutor (offline by default, $0, no key).

**Status:** covered by the offline suite — 557 passing, 16 live-gated, 573 total (`test_unified_ui.py`, `test_ui_openworld.py`,
`test_ui_artifact.py`); the live open-world cold-start was verified end-to-end with a metered smoke.

> Covers all UI modules after the June 2026 pull: open-world cold-start, downloadable artifact,
> recommend-next, and provider-agnostic LLM access (LiteLLM).

## Two modes (one page, chosen by config)

- **Offline / curated** (`LITNAV_LLM_PROVIDER=none`, default — $0, no key): teaches from a curated
  agent-papers corpus seeded at session start. Instant, deterministic — the demo mode.
- **Live / open-world** (any provider configured): a typed goal triggers the full cold start —
  the page streams *finding sources → building your concept map → teaching* as `find_sources` →
  `digest.pipeline` run, then teaches from the freshly-built graph. Provider-agnostic via LiteLLM
  (OpenAI, Anthropic, Gemini, DeepSeek, … — see [BACKEND-COMPLETE](BACKEND-COMPLETE.md)).

A **"Show research detail" toggle** turns the per-step provenance chips (skill · method · paper) on or
off — a plain summary for a learner, the full research chain for an evaluator, on one page.

---

## 1. System Architecture (ASCII)

```
  Browser
  ┌────────────────────────────────────────────────────────────────────┐
  │                                                                    │
  │   /tutor (agent_home.html)                                         │
  │   ┌──────────────────────────┐                                     │
  │   │  Discovery story band    │──── GET /tutor/start?goal=… ───┐   │
  │   │  Intent quick-links      │──── GET /tutor/start?intent=… ─┤   │
  │   └──────────────────────────┘                                 │   │
  │                                                                 │   │
  │   /tutor/{sid} (agent.html)  ←────────── redirect 303 ─────────┘   │
  │   ┌────────────────────────────────────────────────────────┐       │
  │   │   header  [Chat | Glass box]  [Show research detail]   │       │
  │   │   ┌──────────────────┬──────────────────────────────┐  │       │
  │   │   │  #chat (left)    │  #glass (right, opt-in)      │  │       │
  │   │   │  Story band      │  Concept map (SVG)           │  │       │
  │   │   │  Thread bubbles  │  Agent flow steps            │  │       │
  │   │   │  ● working…      │  Learning route (badges)     │  │       │
  │   │   │  Artifact card   │  Cited evidence              │  │       │
  │   │   │  Answer form     │  Learner model (bars)        │  │       │
  │   │   │                  │  Recommend-next              │  │       │
  │   │   │                  │  Why this step               │  │       │
  │   │   │                  │  Induced edges               │  │       │
  │   │   │                  │  Cost                        │  │       │
  │   │   └──────────────────┴──────────────────────────────┘  │       │
  │   └────────────────────────────────────────────────────────┘       │
  │          │ POST /tutor/{sid}/events (fetch + ReadableStream)        │
  │          │ ◄── SSE stream (text/event-stream) ────────────────────  │
  │                                                                    │
  │   /sessions/{sid} (index.html) — judge-facing read-only trace      │
  └────────────────────────────────────────────────────────────────────┘
              │                                │
              ▼                                ▼
  ┌─────────────────────┐         ┌──────────────────────────┐
  │  FastAPI  (server.py)│         │  SQLite (per-session)    │
  │  litnav.ui.server    │────────►│  sessions / route_steps  │
  │  uvicorn 127.0.0.1:8000        │  tutor_turns / decisions │
  └──────────┬──────────┘         │  learner_state / chunks  │
             │                    │  cost_ledger             │
             ▼                    └──────────────────────────┘
  ┌─────────────────────┐
  │  interactive.py      │
  │  TutorSession        │ ──► LangGraph StateGraph
  │  AgentSession        │         ├─ planner
  └──────────┬──────────┘         ├─ orient_tour / goal_elicit
             │                    ├─ select_next / retrieve
             │                    ├─ teach_kp / assess_next
             │                    ├─ grade_kp / reteach_kp
             │                    ├─ advance_kp / route_decider
             │                    └─ replan / diagnose / concede
             │
             ▼ (live / open-world mode only)
  ┌────────────────────────────────────┐
  │  litnav.discover  (find_sources)   │
  │  litnav.digest    (pipeline)       │
  │  litnav.artifact  (make_artifact)  │
  │  litnav.recommend (recommend_next) │
  └────────────────────────────────────┘
```

---

## 2. URL / Route Index

| Method | Path | Template | Description |
|--------|------|----------|-------------|
| `GET` | `/` | `index.html` | Opens the most recent session trace; falls back to a "no sessions" placeholder if empty |
| `GET` | `/sessions/{sid}` | `index.html` | Read-only judge-facing trace panel for any past session |
| `GET` | `/sessions/{sid}/trace` | — | Raw JSON trace (same data as the panel, for debugging/export) |
| `GET` | `/tutor` | `agent_home.html` | Start page — corpus story, intent links, free-text goal form |
| `GET` | `/tutor/start?goal=…&intent=…` | — | Creates a session and redirects to `/tutor/{sid}` (303) |
| `GET` | `/tutor/{sid}` | `agent.html` | Live interactive tutor page |
| `POST` | `/tutor/{sid}/events` | — | SSE event stream; body `{"answer": "…"}` resumes the graph |
| `GET` | `/tutor/{sid}/artifact` | — | Download the session's Markdown take-away (generated at session end) |

**Session lifecycle** (`server.py:_start_agent`):

- **Offline / curated** (default): seeds from `data/seed/agents_*.json`, uses `AgentSession` backed by the fixture.
  - `intent=researcher|journalist` → `TutorSession.start(intent=…)` runs immediately.
  - Explicit teachable goal → `ag._start_teaching(slug)` fires the first teach synchronously.
  - Anything else → conversation mode; teaching starts once the user says enough.
- **Open-world / live** (`LITNAV_LLM_PROVIDER != none` + free-text goal, no intent): builds a fresh per-session concept graph via `AgentSession._build_open_world()` and streams `build` events on first `/events` call. The template sets `window.__BUILDING__ = true` to trigger this on page load.

---

## 3. Templates

### 3.1 `agent_home.html` — Start page

Rendered by `GET /tutor`. Static HTML, no JS.

**Sections:**
- **Hero card** — domain name, paper count, concept count, edge count, 5 representative paper pills. Uses Jinja2 vars from `_story_context()`.
- **Pipeline grid** — 3 cards: Discover · Digest · Teach Live. Explains what was done offline vs live.
- **Goal form** — `<form action="/tutor/start">` with `?goal=` input and pre-filled example links.
- **Intent links** — `?intent=researcher` and `?intent=journalist` anchor links.

Jinja2 variables passed: `story_domain`, `story_paper_count`, `story_concept_count`, `story_edge_count`, `story_representative_papers`, `story_target_names`, `story_concept_names`, `n_papers`, `message`.

### 3.2 `agent.html` — Live tutor page

Full interactive page. Two-column layout: `#chat` (left) and `#glass` (right).

**Header:**
- Session name, paper count, intent badge (muted text).
- Chat / Glass box toggle buttons (persists per-session to `body.mode-chat` / `body.mode-glass`, never across sessions).
- "Show research detail" checkbox — toggles `body.show-detail`; persists to `localStorage`.

**`#chat` column:**
- **Story band** (`.storyband`) — 3 cells: Discover (domain + paper count), Digest (concept map chips), Representative 5 papers. Shown only in offline mode; replaced by an open-world card when `building=true`.
- **Open-world card** — shown when `window.__BUILDING__=true`; auto-fires `streamEvents({})` to trigger cold-start discovery.
- **Thread** (`#thread`) — scrollable chat transcript. Server-rendered bubbles use `data-md` attribute; JS applies `md()` on DOM-ready.
- **Working indicator** (`#working`) — "● agent working…" shown while SSE stream is open.
- **Session-complete card** — appears when `done=true`; contains artifact download link and "full trace →" link.
- **Artifact card** (`#artifact-card`) — injected dynamically by `renderArtifact()` when the SSE stream emits an `artifact` event.
- **Answer form** (`#answer-form`) — `<input>` + Send button; `submitAnswer()` fires on submit.

**`#glass` column (Glass box):**
| Panel | ID | Content |
|---|---|---|
| Concept map | `#cmap` | Inline SVG from `graph_svg.to_svg()` |
| Agent flow | `#flow` | Step list with icons + research-chip provenance |
| Learning route | `#route-list` | Concept sequence with colored status badges |
| Cited evidence | `#evidence` | Chunk IDs + 140-char text snippets |
| Learner model | `#learner` | Mastery + confidence bars per concept; misconceptions |
| Recommend next | `#recommend` | Post-session recommendations from `recommend_next` |
| Why this step | `#why` | Decision label + rationale text |
| Induced | `#induced-panel` | Machine-derived prereq edges (dashed in the SVG) |
| Cost | `#cost` | Token count + USD from `cost_ledger` |

### 3.3 `index.html` — Judge-facing trace panel

Server-rendered, read-only, no JS. Displays the full `build_trace()` output: session metadata, route table, timeline (teach/quiz turns with answers and mastery), evidence list, learner model, decisions, induced edges, induction log.

---

## 4. JavaScript Modules (`agent.html`)

### 4.1 `md(raw)` — Markdown renderer

Lightweight Markdown → HTML converter. Input must be plain text (no prior HTML). Pipeline:
1. HTML-escape `& < >`.
2. Parse lines into typed blocks: `{t:'ol'}` for `1. …`, `{t:'ul'}` for `- / • / *`, `{t:'p'}` for prose.
3. Group consecutive `p` blocks into `<p>…<br>…</p>` paragraphs; flush on list or blank line.
4. Inline: `**bold** → <strong>`, `*italic* → <em>`.

Used in `addBubble` for AI turns and in the DOM-ready handler for server-rendered `[data-md]` bubbles.

### 4.2 `addBubble(cls, text)` — Chat bubble factory

Appends a `<div class="bubble {cls}">` to `#thread`.
- AI bubbles (`cls` includes `"ai"`): `innerHTML = md(text)`.
- User bubbles: `textContent = text` (with `white-space: pre-wrap` via CSS).
- Always scrolls thread to bottom.

CSS classes used: `ai`, `ai qa` (question), `ai boundary` (out-of-scope reply), `me` (user).

### 4.3 `setFlow(steps)` — Agent flow renderer

Rebuilds the `#flow` step list from an array of `{label, detail, state, skill, method, paper}` objects.

- `state`: `done` (✓, green), `active` (▶, highlighted), `pending` (○, muted).
- Research provenance chip (`.research-chip`) shown when `skill/method/paper` are present and `body.show-detail` is on.

### 4.4 `updateGlass(e)` — Glass box state sync

Called on every `state` SSE event. Updates:
- `#route-v` — route version with a CSS flash animation (`vbump`) when version increments.
- `#route-list` — concept sequence; new concepts animate in with `flash-in`.
- `#evidence` — chunk snippets.
- `#learner` — mastery/confidence bars (CSS transition `.5s ease`).
- `#why` / `#why-text` — rationale.
- `#induced-panel` — induced edges.
- `#cmap` — replaces SVG content.
- `#cost` — token count + USD.
- `#recommend` — recommend-next list with lock/checkmark icon.

### 4.5 `handleEvent(e, steps, inp)` — SSE event dispatcher

| Event type | Action |
|---|---|
| `dispatch` | Clears `steps`, pushes first active step, calls `setFlow` |
| `reply` | Marks all steps done, adds AI bubble (boundary variant if `kind==='boundary'`) |
| `step` | Marks prior steps done, pushes new active step with provenance |
| `teach` | Marks steps done, adds AI teaching bubble |
| `question` | Adds AI question bubble (`.qa`) |
| `state` | Calls `updateGlass(e)` |
| `done` | Hides working indicator; if `e.done`, reloads page via `location.href` for clean re-render |
| `build` | Shows discovery/digest/map progress bubbles (open-world cold start only) |
| `artifact` | Calls `renderArtifact(e)` |
| `error` | Reloads page |

### 4.6 `renderArtifact(e)` — Artifact card

Injects into `#artifact-card`: format label, download link (`GET /tutor/{sid}/artifact`), 500-char preview in `<pre>`.

### 4.7 `streamEvents(body)` — SSE fetch loop

`POST /tutor/{sid}/events` with `body` (usually `{answer: "…"}`), reads the `text/event-stream` via `fetch + ReadableStream`, splits on `\n\n`, feeds each `data: …` line to `handleEvent`. Disables the input while streaming, re-enables on `done`. Also used with `{}` on load to drive the open-world build.

### 4.8 `submitAnswer(ev)` — Form handler

Reads the input, adds a user bubble, clears the field, calls `streamEvents({answer: text})`.

### 4.9 `setMode(m)` / `toggleDetail(on)` — View preferences

- `setMode('chat'|'glass')` — switches body class; Chat/Glass box buttons highlight.
- `toggleDetail(on)` — toggles `body.show-detail`; persists to `localStorage['litnav-detail']`.

---

## 5. Python UI Modules

### 5.1 `server.py` — FastAPI application

| Symbol | Role |
|---|---|
| `app` | FastAPI instance, `title="LitNavigator trace panel"` |
| `_TUTORS` | In-memory `{sid: TutorSession}` (legacy, kept for compatibility) |
| `_AGENTS` | In-memory `{sid: AgentSession}` (active live sessions) |
| `_ARTIFACT_DIR` | Base directory for artifact output files (`"artifacts"`) |
| `_TEMPLATES` | Jinja2 environment, autoescape enabled, loads from `litnav/ui/templates/` |
| `_fixture_data()` | Reads `data/seed/agents_expanded.json` (or `agents_m3.json` as fallback) |
| `_story_context(data)` | Builds story-band template vars; picks 5 anchor arXiv papers by ID |
| `_start_agent(goal, intent)` | Creates `AgentSession`, per-session SQLite DB + checkpoint DB; dispatches to open-world vs. curated path |
| `session_page` | Renders `index.html` with `build_trace()` data |
| `tutor_home` | Renders `agent_home.html` with story context |
| `tutor_start` | Calls `_start_agent`, redirects 303 |
| `tutor_page` | Renders `agent.html` with `ag.current()` and story context; passes `artifact_url` if one exists |
| `tutor_events` | Async; reads JSON body `{answer}`, calls `ag.handle(message)` or `ag.current_events()`, streams as SSE |
| `tutor_artifact` | Serves the Markdown artifact via `FileResponse` with `Content-Disposition: attachment` |

### 5.2 `interactive.py` — Session orchestration

**`TutorSession`** — wraps a single `LangGraph` `StateGraph`.

| Method | Description |
|---|---|
| `__init__` | Builds graph with `interrupt_after=["check","assess_next"]`; per-session SQLite + checkpoint; `out_dir` for artifacts |
| `start(topic, …, goal_text=…)` | `app.invoke(initial_state)`, returns `current()`; `goal_text` drives depth elicitation |
| `answer(text)` | `update_state({user_answer, pending_answers:[]})` + `app.invoke(None)` to resume; returns `current()` |
| `stream_answer(text)` | Like `answer` but yields step events as they fire (for `streamEvents` in the browser) |
| `current()` | Reads checkpoint + DB; returns live glass-box snapshot dict |
| `_terminal_events()` | Assembles the full event list to send after a graph pause: `teach` events, `question`, `state`, optional `artifact`, `done` |
| `_recommend()` | Calls `recommend_next(conn, sid)`; returns serialisable list |
| `_artifact_event()` | Generates the take-away artifact **once** at session end via `make_artifact`; sets `artifact_path` |

**`AgentSession`** — conversation wrapper; holds a `TutorSession` once teaching starts.

| Mode | Behaviour |
|---|---|
| Offline curated (default) | Seeds from fixture, wraps `TutorSession` for intent/goal start |
| Open-world live | `open_world=True`; `_build_open_world()` yields `build` events → `find_sources` → `digest.pipeline` → repopulates `concepts` → creates `TutorSession` |
| Conversing (no target yet) | `handle(message)` calls `dispatch()` to classify intent; triggers `_start_teaching(slug)` on `concept`/`induce` kind |

Key attributes: `conn` (domain DB), `ckpt` (checkpoint DB), `tutor` (`TutorSession | None`), `open_world`, `built`, `goal`, `out_dir`.

### 5.3 `trace.py` — Pure-data trace builder

**`concept_graph(conn, session_id)`** — returns `{nodes, edges}` for the SVG renderer. Node states: `idle`, `current` (first pending route step), `mastered` (done), `conceded`, `lectured`. Edge source distinguishes `curated` vs `induced` (dashed).

**`build_trace(conn, session_id)`** — assembles the full judge-facing dict:

| Key | Content |
|---|---|
| `session` | id, topic, status |
| `route` | step list (concept_id, name, status, reason) |
| `route_version` | latest version number |
| `concepts` | learner state per concept (mastery, confidence, held misconceptions) |
| `decisions` | all `decisions` rows in order |
| `tutor_turns` | all `tutor_turns` rows (cited chunks, strategy, pre/post score, mastery_after) |
| `timeline` | chronological view pairing ROUTING decisions with quiz attempts and lecture events |
| `evidence` | deduplicated cited chunk texts |
| `induced_edges` | machine-derived prereq edges |
| `induction` | induction log entries |
| `total_token_cost` | sum of all turn + decision token costs |

Timeline construction rule: `advance / reteach / diagnose / replan / concede` decisions pair 1:1 with `tutor_turns` + `quiz_attempts` in order; `lecture` decisions create a standalone entry with no answer or mastery.

### 5.4 `graph_svg.py` — Concept map renderer

Converts a `concept_graph()` dict to an inline SVG with no external dependencies.

- **Layout**: longest-path layering (prereqs on the left), nodes sorted by id within each column.
- **Node fill**: `idle` (grey), `current` (purple), `mastered` (green), `conceded` (pink), `lectured` (blue-grey).
- **Node stroke**: `consensus` (green), `contested` (amber), `open` (red); `current` gets the accent purple at 3px.
- **Induced nodes/edges**: `stroke-dasharray="5 3"` / `"4 3"` dashed.
- **Edges**: cubic Bézier curves, arrow head via `<marker>`.
- Output embedded directly via Jinja2 `{{ graph|safe }}` and updated via `document.getElementById('cmap').innerHTML = e.graph`.

### 5.5 `flow_meta.py` — Node provenance registry

Maps every graph node name to `{skill, method, paper}` for the research-detail chip in `#flow`.

Coverage: goal_elicit, planner, orient_tour, retrieve, init_kp, teach_kp, assess_next, grade_kp, reteach_kp, advance_kp, handle_lost, diagnose, replan, select_next, induce, induce_scaffold, teach, check, grade, lecture, reteach, concede, advance.

Used by `TutorSession._step_event()` to attach provenance to every `step` SSE event.

### 5.6 `cost.py` — Session cost calculator

**`session_cost(conn, sid) → {tokens, usd}`**

- Primary source: `cost_ledger` table (written by the LLM router for every metered call — discover, digest, teach, grade, artifact). Offline sessions show `$0`.
- Fallback: legacy `tutor_turns.token_cost` summed with blended `$0.0004/1K` rate.

---

## 6. SSE Event Schema

All events are JSON objects. The client receives them via `POST /tutor/{sid}/events`.

```
{ type: "dispatch",  label: "…" }
{ type: "step",      label: "…", detail: "…", node: "…",
                     skill: "…", method: "…", paper: "…" }
{ type: "teach",     text: "…", cited: [{chunk_id, text}] }
{ type: "question",  text: "…", bloom_level: "…" }
{ type: "reply",     text: "…", kind: "boundary"|undefined }
{ type: "state",     route: […], route_version: N,
                     learner: […], cited: […],
                     decision: "…", rationale: "…",
                     induced: […], intent: "…",
                     graph: "<svg…>", cost: {tokens, usd},
                     recommend: [{concept_id, name, reason, eligible, score}] }
{ type: "done",      done: true|false, mastery: 0.0–1.0, confidence: 0.0–1.0 }
{ type: "artifact",  format: "notes|slides|…", url: "/tutor/{sid}/artifact",
                     citations: […], preview: "…" }
{ type: "build",     stage: "discover"|"discover_done"|"digest"|"map",
                     label: "…", graph?: "<svg…>",
                     skill: "…", method: "…", paper: "…" }
{ type: "error",     message: "…" }
```

---

## 7. CSS Design Tokens

Defined in `:root` and reused across both templates:

| Token | Value | Meaning |
|---|---|---|
| `--accent` | `#5b49c4` | Primary purple (buttons, current-concept stroke, mastery bar) |
| `--ok` | `#258a51` | Green (mastered status, consensus frontier, done step icon) |
| `--warn` | `#b3700d` | Amber (conceded, contested frontier, route-version bump) |

Other key colors: `#1c2430` (dark header background), `#cf4f24` (open frontier, conceded stroke), `#7fd1a6` (confidence bar fill).

---

## 8. Fixture / Seed Data Flow

```
data/seed/
  agents_m2.json      ← minimal 2-concept fixture (ReAct only; used in unit tests)
  agents_m3.json      ← 7-concept curated pack (standard demo)
  agents_expanded.json← 7-concept + expanded evidence (preferred when present)
  agents_reroute.json ← 3-concept reroute fixture (reroute tests)

server.py:_TUTOR_FIXTURE → agents_expanded.json (or m3 fallback)
server.py:_fixture_data() → parsed JSON, passed to AgentSession
server.py:_story_context() → extracts story-band vars from the same JSON
AgentSession.__init__ → seed_demo_data(conn, fixture_path) writes to per-session SQLite
```

Open-world sessions skip the fixture entirely; `find_sources` + `digest.pipeline` build the same tables live.

---

## 9. Verification

| What | How |
|---|---|
| Server render + SSE provenance/recommend payload | `tests/test_unified_ui.py` (FastAPI TestClient + `flow_meta` assertions) |
| Open-world build path + no-source boundary | `tests/test_ui_openworld.py` (monkeypatched discover/digest, offline/$0) |
| Artifact generation + download endpoint | `tests/test_ui_artifact.py` |
| **Full offline suite** | `python -m pytest -q` → **557 passed, 16 live-gated (573 total)** ($0) |
| **Live open-world (metered smoke)** | a fresh "CRISPR" goal streamed `discover → digest → map (4 concepts) → teach → quiz` through the UI for **$0.0065** (18 calls); the cost meter reported it from `cost_ledger` |
