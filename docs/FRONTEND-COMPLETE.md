# Frontend — What Ships Today

*The unified glass-box + learner web UI: one page that teaches a real learner **and** exposes the full
agent reasoning (skill · method · paper · live scores) for a technical viewer.* Backend it talks to:
[BACKEND-COMPLETE](BACKEND-COMPLETE.md). Remaining work: [FRONTEND-ROADMAP](FRONTEND-ROADMAP.md).

**Run it:** `python -m litnav.ui.server` → open http://127.0.0.1:8000/tutor (runs fully offline, $0, no key).

---

## One page, two audiences

The session page `GET /tutor/{sid}` puts the conversation and the "glass box" side by side, so the
same screen serves a lay learner and a technical evaluator:

- **Chat (left):** the teaching conversation — explanations, quiz questions, the learner's answers,
  feedback, artifacts, and the recommend-next card at the end.
- **Glass box (right):** the live agent reasoning — the agent-flow timeline, the concept map, the
  learning route, cited evidence, the learner model (mastery/confidence), the "why this step"
  rationale, the cost meter, and the recommend-next breakdown.

A **"Show research detail" toggle** turns the per-step provenance chips (skill · method · paper) on or
off — a plain summary for a learner, the full research chain for an evaluator, on one page.

## What the glass box shows

| Panel | What it shows | Source |
|--|--|--|
| **Agent flow** | Each step the agent ran (teach / quiz / grade / re-explain / advance …), each with **skill · method · paper** chips when "research detail" is on | `litnav/ui/flow_meta.py` (`NODE_META` maps every graph node → `{skill, method, paper}`), streamed in the SSE `step` events |
| **Concept map** | The session's concept graph as inline SVG; solid = prerequisite, dashed = similarity, dotted = induced; node colour = route status (current / mastered / conceded / lectured) | `litnav/ui/graph_svg.py` |
| **Learner model** | Per-concept mastery (BKT, 0–1) and confidence, shown as an **estimate** (never a claim of durable learning) | `litnav/ui/trace.py::build_trace` reading `learner_state` |
| **Cited evidence** | The source chunks each teaching turn cited, with paper title — chunk ids resolve to real `paper_chunks` | `build_trace` |
| **Why this step** | The rule-computed routing rationale for the current decision | graph state |
| **Cost meter** | Cumulative USD for the session, from the cost ledger | `litnav/ui/cost.py` |
| **Recommend next** | At session end: ranked next concepts, each "ready now — unlocks N" or "blocked — needs X first" | `litnav/recommend/recommend_next.py` |

## How it updates (streaming)

The learner submits an answer; the page POSTs it to `POST /tutor/{sid}/events` and consumes a
**Server-Sent-Events stream** (`fetch` + `ReadableStream`). The backend streams one event per graph
node as it executes (`type:"step"` with the skill/method/paper provenance), then the terminal
teach / question / state / done events; the chat and glass box update together as events arrive.
(`litnav/ui/interactive.py` produces the events; `litnav/ui/server.py` serves the stream.)

## Routes

| Route | Purpose |
|--|--|
| `GET /tutor` | Landing page — enter any goal; shows the available topics |
| `GET /tutor/{sid}` | **Main session page** (chat + glass box, live SSE) |
| `POST /tutor/{sid}/events` | SSE stream of agent steps + state for a turn (answer in the JSON body) |
| `GET /sessions/{sid}` | Legacy read-only trace panel (closed-world `demo-m2`/`demo-m3` runs) |

## Offline-deterministic demo

The whole UI runs without an LLM key against the curated agent-paper fixture
(`data/seed/agents_expanded.json`), seeded into a fresh per-session SQLite DB at start. This is enough
to walk the full teach → assess → artifact → recommend-next loop at $0 for a demo; pointing the server
at a live provider swaps in real discovery/digest/teaching.

## Key files

| File | Role |
|--|--|
| `litnav/ui/server.py` | FastAPI app — routes, session lifecycle, SSE handler |
| `litnav/ui/interactive.py` | `AgentSession` / `TutorSession` — drive the graph, emit UI events |
| `litnav/ui/flow_meta.py` | `NODE_META` — per-node skill / method / paper provenance |
| `litnav/ui/trace.py` | `build_trace()` — per-session DB → structured trace |
| `litnav/ui/graph_svg.py` | concept-map SVG |
| `litnav/ui/cost.py` | session cost summary |
| `litnav/ui/templates/agent.html` | the unified session page |
| `litnav/ui/templates/agent_home.html` | the landing page |

## Verified
Server-side rendering + the SSE provenance/recommend payload are covered by `tests/test_unified_ui.py`
(TestClient + `flow_meta` assertions), part of the 353-test suite; the unified page was also confirmed
in-browser (agent-flow chips carry the right skill/method/paper; recommend-next renders ready/blocked).
