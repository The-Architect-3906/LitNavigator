# LitNavigator — Frontend Roadmap

**Branch:** `feat/open-world-digest` · **Updated:** 2026-06-21

What remains after the OW-6 P6 unified frontend lands. Items marked P0 (demo-blocking), P1
(high), P2 (medium), or **deferred** (post-MVP). Backend counterparts are in
[`BACKEND-ROADMAP.md`](BACKEND-ROADMAP.md).

---

## Session persistence and auth (P1)

The current session model is per-process and ephemeral: each `AgentSession` lives in an
in-memory dict (`_AGENTS`) keyed by a UUID, backed by a per-session SQLite file under
`data/runtime/`. Restarting the server loses all active sessions.

What is needed:
- **Persistent session registry:** index all per-session SQLite files so the server can
  reconstruct `_AGENTS` on restart.
- **Session list page:** a `/sessions` view that lists all past sessions with topic, status,
  date, and overall quality score (from `cost_ledger` and the E2E judge).
- **Auth (minimal):** at minimum a single-user passphrase gate so the demo UI is not open to
  the world when hosted. Multi-user accounts are post-MVP.
- **Resume:** `/tutor/{sid}` for a completed or paused session re-loads from the persisted
  SQLite and continues from the LangGraph checkpoint (`SqliteSaver`).

---

## Streamed digest progress (P0 for OW-7 demo)

When OW-7 live cold-start digest runs, the UI currently shows nothing until the digest
completes. For the demo this is unacceptable — it needs to stream progress:

- **Stage banners:** "Finding sources…", "Extracting concepts…", "Building concept map…",
  "Verifying edges…" — emitted as SSE events from the digest pipeline stages in
  `litnav/digest/pipeline.py`.
- **Partial graph preview:** render the concept-map SVG incrementally as concepts are
  extracted, before edges are verified.
- Requires OW-7 backend work to emit progress events; the frontend SSE handler already
  exists (it polls the trace endpoint) but needs to subscribe to a new
  `/tutor/{sid}/events` endpoint that yields digest-progress events.

---

## Teacher-override controls (P1)

The glass-box is currently read-only. Adding teacher-override controls:
- **Edge approval / rejection:** thumbs-up / thumbs-down on a displayed prereq edge
  → writes `concept_edges.human_checked = 1` or marks the edge `similarity`.
- **Concept reorder:** drag-and-drop concept sequence in the prereq route before teaching
  starts.
- **Bloom ceiling override:** a dropdown on the session landing page to set `goal_type`
  explicitly (currently only set by the LLM goal-elicit node).

These require new `PUT /sessions/{sid}/edges/{edge_id}` and
`PUT /sessions/{sid}/goal` API endpoints, thin backend repo helpers, and wiring into the
LangGraph state (an override clears the relevant graph node's cached decision).

---

## Artifact download (P1)

Artifacts are written to `artifacts/<session_id>/<format>.md` by `make_artifact.py`. The UI
does not yet surface them as downloadable files. Need:
- An artifact card in the chat pane with a **Download** button.
- A `GET /sessions/{sid}/artifact/{format}` endpoint that streams the `.md` file (or a
  rendered HTML/PDF via `marp-cli` post-step for slides).
- **Marp → PPTX:** the `marp-cli` post-step (`marp --pptx artifact.md`) is the cleanest path
  for editable slides. Requires `marp-cli` installed in the environment (Node.js dependency);
  the backend emits the `.md`, the endpoint invokes `marp-cli` on demand and streams the
  resulting `.pptx`.

---

## Quality scores surfaced live (P1)

The frontier gpt-4o judge scores (source_relevance, quiz_quality, feedback_quality, etc.) are
currently computed only in the offline E2E harness (`inner_loop_scenarios.py`). Making them
visible during a live session:
- **Per-turn feedback score:** after each quiz + grade turn, run a cheap-tier self-evaluation
  ("was this quiz question clear and relevant?") and display the score as a colored dot in the
  glass-box.
- **Session summary panel:** at session end, trigger a frontier judge call (opt-in, metered)
  and display the dimension breakdown as a radar chart.
- This requires a new `evaluation/live_judge.py` (a subset of `inner_loop_scenarios.py`'s
  judging logic) and a `POST /sessions/{sid}/judge` endpoint.

---

## Richer streaming and progress (P1)

Beyond digest streaming (above):
- **Token-by-token streaming** for teach and reteach turns (currently the full `teach_kp`
  response is emitted at once). Requires the LLM router to support streaming mode
  (`client.stream_text`) and the FastAPI endpoint to relay chunks as SSE.
- **Bloom ladder visualization:** show the current Bloom level as a colored step in the
  glass-box as it advances within a concept.

---

## Mobile polish (P2)

The current UI is a desktop-first two-column layout (chat | glass-box). On mobile:
- Collapse the glass-box into a collapsible drawer or tab bar.
- Make the chat pane full-width by default.
- Ensure the recommend-next card is readable on narrow viewports.

No CSS framework is currently used (the templates use inline styles and a minimal `<style>`
block in `agent.html`). Adding Tailwind or a CSS reset would be the easiest path.

---

## Deployment (P2)

The current setup is a local `uvicorn` server (implicit in `python -m litnav.ui.server`).
For the ICCSE demo or any shared hosting:
- **Docker image:** `Dockerfile` that installs Python deps, seeds demo data, and starts
  `uvicorn litnav.ui.server:app --host 0.0.0.0 --port 8000`.
- **Environment variables:** `LITNAV_LLM_PROVIDER`, `LITNAV_LLM_API_KEY`, `LITNAV_DB_PATH`
  (to mount a persistent volume).
- **Offline-only demo:** set `LITNAV_LLM_PROVIDER=none` to run the curated fixture at $0
  with no key needed — the correct default for a public demo.
- A `docker-compose.yml` with a single service is sufficient for the competition demo.

---

## Priority summary

| Item | Priority |
|---|---|
| Streamed digest progress (OW-7 SSE events) | P0 |
| Session persistence + resume | P1 |
| Teacher-override controls (edge approval, reorder, Bloom override) | P1 |
| Artifact download (`.md` + Marp→PPTX) | P1 |
| Quality scores surfaced live (per-turn + session judge) | P1 |
| Token-by-token streaming (teach/reteach) | P1 |
| Bloom ladder visualization | P1 |
| Mobile polish (collapsible glass-box) | P2 |
| Deployment (Docker + env-var config) | P2 |
