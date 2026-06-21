# Frontend — What's Next

*The remaining frontend work, in priority order, in plain language.* What already ships:
[FRONTEND-COMPLETE](FRONTEND-COMPLETE.md). The backend items these depend on:
[BACKEND-ROADMAP](BACKEND-ROADMAP.md).

Each item is tagged **P0** (blocks the competition demo), **P1** (high value), **P2** (nice to have),
or **deferred** (post-MVP).

---

## 1. Stream the cold-start digest to the screen — *P0*

When a brand-new topic is digested live, the page currently shows nothing until the whole map is
built. For the demo it needs to narrate the build:

- **Stage banners** — "Finding sources… → Extracting concepts… → Building the map… → Verifying
  links…" — shown as they happen.
- **Map grows live** — render the concept-map SVG incrementally as concepts appear, before the
  prerequisite links are verified.

The page already consumes a Server-Sent-Events stream over `POST /tutor/{sid}/events` for the
teaching loop; this item extends that same stream to carry the digest-pipeline progress events
(which the backend's live cold-start work must emit — see [BACKEND-ROADMAP](BACKEND-ROADMAP.md)).

## 2. Save and resume sessions — *P1*

Sessions are currently in-memory and ephemeral: each lives in a process dict keyed by a UUID, backed
by a per-session SQLite file under `data/runtime/`. Restarting the server loses every active session.

- **Persistent session registry** so the server can rebuild its session list on restart by indexing
  the per-session SQLite files.
- **A "past sessions" page** (`/sessions`) listing each session's topic, status, date, and quality
  score.
- **Resume** — opening a finished or paused session reloads it from SQLite and continues from the
  saved LangGraph checkpoint.
- **Minimal auth** — at least a single passphrase gate before hosting the demo publicly. Real
  multi-user accounts are post-MVP.

## 3. Download the take-away artifact — *P1*

Artifacts are written to `artifacts/<session_id>/<format>.md` but the UI doesn't yet offer them for
download.

- A **Download** button on the artifact card in the chat pane.
- An endpoint that streams the artifact file.
- **Slides → PowerPoint:** convert the slide artifact to an editable `.pptx` on demand via `marp-cli`
  (a Node.js tool) — the backend emits Markdown, the endpoint renders it when requested.

## 4. Teacher-override controls — *P1*

The glass box is read-only today. Letting an instructor steer it:

- **Approve / reject a prerequisite link** with a thumbs-up / thumbs-down (writes back to the edge,
  marking it human-checked or demoting it to a plain similarity link).
- **Reorder concepts** by drag-and-drop before teaching starts.
- **Set the depth ceiling** explicitly from a dropdown, overriding the automatic goal classification.

Each needs a small write endpoint, a thin storage helper, and a way to clear the affected graph
node's cached decision.

## 5. Quality scores during a live session — *P1*

The frontier-judge dimension scores (source relevance, quiz quality, feedback quality, …) are
computed only in the offline evaluation harness today. Surfacing them live:

- **Per-turn dot:** a quick cheap-tier self-check after each quiz ("was this question clear and
  on-topic?") shown as a coloured dot in the glass box.
- **End-of-session summary:** an opt-in, metered frontier-judge pass at the end, shown as a
  dimension breakdown (e.g. a radar chart).

## 6. Richer streaming — *P1*

- **Token-by-token teaching:** stream explanations as they generate instead of showing each turn all
  at once (needs streaming support in the LLM router and the SSE relay).
- **Bloom-level indicator:** show the current question difficulty level advancing within a concept.

## 7. Mobile polish — *P2*

The layout is desktop-first (chat | glass box side by side). On a phone: collapse the glass box into a
drawer or tab, make chat full-width, and ensure the recommend-next card reads well on a narrow screen.
The templates use inline styles today; a small CSS reset or utility framework would be the easiest path.

## 8. Deployment — *P2*

For shared hosting or the competition machine: a Docker image that installs dependencies, seeds the
demo data, and starts the server; environment variables for provider/key/DB path; and a one-service
compose file. Default the hosted demo to the offline fixture ($0, no key needed).

## Priority summary

| Item | Priority |
|--|--|
| Stream cold-start digest progress | P0 |
| Save & resume sessions (+ minimal auth) | P1 |
| Artifact download (Markdown + slides→PPTX) | P1 |
| Teacher-override controls | P1 |
| Live quality scores (per-turn + end-of-session) | P1 |
| Richer streaming (token-by-token, Bloom indicator) | P1 |
| Mobile polish | P2 |
| Deployment (Docker + env config) | P2 |
