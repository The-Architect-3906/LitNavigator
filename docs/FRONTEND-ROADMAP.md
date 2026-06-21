# Frontend — What's Next

*The remaining frontend work, in priority order, in plain language.* What already ships:
[FRONTEND-COMPLETE](FRONTEND-COMPLETE.md). The backend items these depend on:
[BACKEND-ROADMAP](BACKEND-ROADMAP.md).

Each item is tagged **P0** (blocks the competition demo), **P1** (high value), **P2** (nice to have),
or **deferred** (post-MVP).

---

## 1. Live open-world cold start in the UI — ✅ shipped

When a live provider is configured, a typed goal now builds the learner's own graph from real
sources, streaming coarse stage banners (*Finding sources… → reading the source → building your
concept map…*) over the existing SSE channel before teaching. See
[FRONTEND-COMPLETE](FRONTEND-COMPLETE.md) → *Two modes*.

**Still polish-worthy (P2):** the map appears in one step once digest finishes — rendering it
*incrementally* (concepts as they're extracted, before edges are verified) would make the wait feel
shorter. Finer-grained stages depend on the digest pipeline emitting sub-step progress
(see [BACKEND-ROADMAP](BACKEND-ROADMAP.md)).

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

## 3. Download the take-away artifact — ✅ shipped (Markdown)

The session now generates a take-away artifact at the end and offers it for download: a Download card
in the chat pane + a persistent link on the completed page, backed by `GET /tutor/{sid}/artifact`
(`make_artifact` runs once at session end).

**Still remaining (P1):** **Slides → PowerPoint** — convert the slide artifact to an editable `.pptx`
on demand via `marp-cli` (a Node.js tool); the backend emits Markdown, the endpoint would render it on
request. Deferred because it adds a Node dependency.

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
| Live open-world cold start in the UI | ✅ shipped |
| Artifact download (Markdown) | ✅ shipped |
| Save & resume sessions (+ minimal auth) | P1 |
| Artifact slides → PPTX (marp) | P1 |
| Teacher-override controls | P1 |
| Live quality scores (per-turn + end-of-session) | P1 |
| Richer streaming (token-by-token, Bloom indicator) | P1 |
| Incremental concept-map render during build | P2 |
| Mobile polish | P2 |
| Deployment (Docker + env config) | P2 |
