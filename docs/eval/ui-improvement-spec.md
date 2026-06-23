All confirmed: `rbadge-active` exists but `rbadge-lectured` does not (dead CSS / invisible dot), no `prefers-reduced-motion`, no `aria-live`, no `role="progressbar"`, three `location.href` reload-on-error sites, and `agent_home.html` has no viewport meta. Here is the spec.

---

# LitNavigator Tutor — Prioritized UI Improvement Spec

## 1. Executive read — how usable is it today

**Verdict: the engine is strong, the cockpit is broken.** LitNavigator's pedagogy (ORIENT→TEACH→ASSESS, rising-Bloom quizzes, rule-computed mastery, induced prereqs, honest boundary replies) is sound and largely working in state. But the UI that exposes it — the chat pane plus the glass box — fails at the two moments that decide a first impression: **the cold start** and **the first graded answer.** A judge or first-time learner currently hits a ~56s wait behind a static "● agent working…" line, then answers a quiz and gets *no feedback at all*, then opens a glass box that reads mostly empty. The product's entire differentiator — "show your work, grounded and adaptive" — is precisely what the UI hides.

**What hurts most, in order:**

1. **No answer feedback in chat (blocker).** After grading, the chat just shows a new question. The "correct/wrong + why" result lands only in `_step_event` detail, which renders *only* in the glass box — and the glass box is `display:none` by default in chat mode. The core teach→assess→**feedback** loop is invisible to the default user. This is the single most damaging bug.

2. **DISCOVER can teach the wrong topic with full confidence (blocker).** "Understand ReAct" built a course on ad-intrusiveness; "how do agents plan" built one on graph pathfinding — narrated as authoritative ("In our upcoming lessons we'll explore Ad Content Congruence…") with no "is this the right source?" gate. A confidently-wrong tutor is worse than a slow one.

3. **The glass box reads empty exactly when it's first opened.** Learner bars filter on `n_observations>0` (interactive.py:280), so lectured/pre-quiz concepts show nothing; `AgentSession.current()` omits `cost` and `recommend` (lines 331-348) that `_terminal_events` includes (159-160), so first paint differs from post-SSE state and panels flicker empty→full. Cited-evidence has no `{%else%}`. The "glass box / cited evidence" value prop renders as blank cards.

4. **Adaptive reasoning is invisible or jargon.** Decision rationale shows raw route tokens (`reteach —`, `concede —`); `concede` reads as the tutor quitting. Quiz bubbles are indistinguishable from teaching (`.qa{font-weight:500}` only), the streamed `bloom_level` is never rendered, and the spaced-retrieval recap (`review_probe` interrupt) has no framing — a repeat question reads as a bug, not deliberate retrieval practice.

5. **Failure and accessibility are unhandled.** Any mid-stream error does `location.href` (3 sites in agent.html) — a blind reload that discards the transcript and never shows `e.message`. `agent_home.html` has **no viewport meta** (first screen a phone hits is broken), no `<h1>`, color-only status throughout, no `prefers-reduced-motion`, no `aria-live`, no `role="progressbar"`.

The good news: nearly all the data needed to fix these already flows through `current()` / `_terminal_events` / `trace.py`. Most fixes are **wiring and presentation, not new pipeline work.** The two blockers (feedback event, DISCOVER gate) are the only items that touch `interactive.py` logic meaningfully.

---

## 2. Top 10 improvements (ranked by impact × 1/effort)

> Effort: S = <1hr, M = a few hrs, L = a day+. Each cites the sweep finding it closes.

### 1. Emit a learner-facing feedback bubble on grade
- **What:** On `grade`/`grade_kp`, yield a `{type:'reply', kind:'feedback', text:'Correct — …' | 'Not quite — …'}` event and render it as a distinct chat bubble (green check / amber), carrying `last_feedback` + `last_detected_misconception`.
- **Why / principle:** Closes the teach→assess→**feedback** loop. Instant, framed feedback is the table-stakes pattern in every course player (Udemy/Coursera "Knowledge Check"). Right now grading is silent.
- **Where:** `interactive.py` `stream_answer` (~194) + `_step_event` (92-96, data already computed); render in `agent.html handleEvent` with a new `feedback` branch + bubble class.
- **Effort:** S–M. **Inspired by:** Coursera/Udemy knowledge checks. **(closes blocker #1)**

### 2. Gate DISCOVER on relevance; confirm or decline honestly
- **What:** After `discover_done`, show the chosen source title + a relevance signal and require confirm before digesting (or surface top-3 to pick). Below a relevance threshold, decline honestly instead of teaching a mismatched topic.
- **Why / principle:** Grounding-made-visible is NotebookLM's core trust mechanic; a confident wrong source destroys it. Reinforces the existing out-of-corpus honesty behavior.
- **Where:** `interactive.py` `_build_open_world` (~359-406) where `withft[0]` is picked silently; add a confirm interrupt + a "no relevant source" boundary reply.
- **Effort:** M. **Inspired by:** NotebookLM persistent-sources grounding. **(closes blocker #2)**

### 3. Designed empty states + symmetric first paint for all glass-box panels
- **What:** (a) Add `cost` and `recommend` to `AgentSession.current()` so Jinja first-paint matches SSE `updateGlass`. (b) Include **all route concepts** in `learner[]` with a "not yet assessed" state instead of filtering on `n_observations`. (c) Give every panel explicit empty copy ("No citations yet — they appear as I teach each keypoint"; "Mastery builds after your first answer") rather than `–`/blank/`display:none`.
- **Why / principle:** NN/g: 92% of AI dashboards lack empty states and read as broken. An honest "not grounded yet" is better than whitespace for a glass-box product.
- **Where:** `interactive.py current()` lines 274-281 (learner filter) + 331-348 (`AgentSession.current()` missing keys); `agent.html` evidence loop (no `{%else%}`), learner loop, cost card.
- **Effort:** S–M. **Inspired by:** NotebookLM honest-grounding + NN/g empty-state research. **(closes the "panels read empty" gap; minor sweep findings across both panels)**

### 4. Rewrite decision rationale as plain-language "why this next" cards
- **What:** Map each route token to a learner sentence: `advance`→"You passed — moving on"; `reteach`→"Let's try this a different way"; `diagnose/replan`→"Adding a prerequisite first"; `concede`→"Marking this not-yet and continuing honestly"; Bloom step-up→"Stepping up to apply-level." Render as a small card under the relevant AI bubble; keep raw token behind the existing detail toggle. Fix the dangling em-dash (Jinja vs JS formatter mismatch) and clear the card when rationale is empty.
- **Why / principle:** XAI research: a one-line, personalized "why did the AI choose this" raises trust and learning outcomes. A glass box only earns trust if the box is readable.
- **Where:** `flow_meta.py` / a presenter in `interactive.py` (map before emit); `agent.html` `#why`/`#why-text` (Jinja ~243 vs JS ~428).
- **Effort:** S. **Inspired by:** ChatGPT/Claude XAI rationale + Eleken XAI patterns. **(closes the dev-jargon-rationale gap)**

### 5. Style quiz bubbles as labeled "Knowledge Check · {Bloom}" cards
- **What:** Give question bubbles a header chip rendering the already-streamed `bloom_level` ("QUESTION · recall") and a left-accent border distinct from teaching, mirroring the `.ai.boundary` treatment. When a question is pending, caption the input "Your answer" and swap placeholder to "Type your answer…".
- **Why / principle:** Unlabeled output is invisible value; framed, low-stakes checks succeed. Surfaces the rising-Bloom progression the product promises but never shows.
- **Where:** `agent.html` `.qa` (~35), `handleEvent` 'question' branch (drops `e.bloom_level` ~482), answer-input (~165).
- **Effort:** S–M. **Inspired by:** Udemy/Coursera knowledge checks. **(closes the "questions look like teaching" + "input has no mode" findings)**

### 6. Staged build progress: 4-step tracker replacing the dead-air spinner
- **What:** Replace the static "● agent working…" with a fixed 4-row stepper (Discover sources → Digest into map → Plan route → Start teaching) where each row flips to a check with a result count ("14 sources", "23-concept map") as its `build` SSE event lands; current row pulses; add an elapsed timer and finer sub-stage events during the ~31s digest. Animate the dot; honor `prefers-reduced-motion`.
- **Why / principle:** NN/g: 100% of AI dashboards use a generic spinner; staged progress raises tolerated wait time and avoids "did it freeze?" during the two long gaps. Don't autofocus the input you immediately disable.
- **Where:** `agent.html` `#working` + `.working` (no animation) + `__BUILDING__` path; reuse `.step`/`setFlow` markup; `interactive.py _build_open_world` stage cadence (emit sub-stage events).
- **Effort:** M. **Inspired by:** Smart Interface Design staged loading / NN/g. **(closes blocker-adjacent "56s dead air" major finding)**

### 7. Inline numbered citation chips → expandable source cards
- **What:** Render `[1][2]` superscripts in teach bubbles keyed to the `cited[]` already on each teach event; clicking activates the Cited-evidence tab and scroll-highlights the matching card. Replace raw `chunk_id: text…` cards with a titled card showing **paper title** (drop/demote chunk_id), only append "…" when actually truncated.
- **Why / principle:** NotebookLM's single biggest trust mechanic — every claim auditable. Also gives the evidence panel a reason to populate, fixing its empty-read.
- **Where:** `agent.html` `handleEvent` 'teach' (ignores `e.cited` ~479) + `md()` renderer; `#evidence` cards; data already in `current().cited` (266-271) and teach events (149).
- **Effort:** M. **Inspired by:** NotebookLM inline citations + ChatGPT/Claude source cards. **(closes "teaching bubbles never show citations" + "evidence shows raw chunk ids")**

### 8. Frame the spaced-retrieval recap as a distinct "Recap" moment
- **What:** Add a `review_probe` label to `_STEP_LABELS`; tag its question event `kind:'recap'`; render a distinct badge ("Quick recall — revisiting X from earlier to lock it in") with its own accent, and mark the revisited concept in the route/map.
- **Why / principle:** Spacing+retrieval (Nature Reviews Psychology 2022) only pays off if the learner experiences it *as* deliberate recall; unlabeled, it reads as a repeat bug.
- **Where:** `interactive.py` `_STEP_LABELS` (60), question event in `_terminal_events` (154); `agent.html` question bubble styling.
- **Effort:** S. **Inspired by:** NotebookLM labeled modes + spaced-retrieval science. **(closes the recap-framing gap)**

### 9. Inline error recovery with Retry (kill the blind reload)
- **What:** Replace all three `location.href='/tutor/'+SID` sites with an inline dismissible error bubble showing `e.message` + a Retry button that re-runs `streamEvents` with the last body, and re-enable the input. Reserve reload for unrecoverable cases.
- **Why / principle:** NN/g: 78% of AI dashboards have no error state; good ones say what broke, what to do, the path back. Today a network blip during the 56s build silently nukes the transcript.
- **Where:** `agent.html` `streamEvents` catch (~545) + 'error' handler (~504) + the third reload site (~489); `server.py` already emits `{type:'error',message}`.
- **Effort:** S–M. **Inspired by:** Canvas/Artifacts streaming UX + NN/g error states. **(closes "error handling nukes the chat")**

### 10. Persistent route rail with status glyphs + "X of N mastered" header
- **What:** Promote the ORIENT roadmap from a one-time tour into a persistent rail: one row per keypoint with a state glyph (done/current/locked/needs-reteach), current row marked, a pinned "X of N keypoints mastered" bar, and a `.rbadge-lectured` color (currently dead CSS → invisible dot). Reconcile route vocab (`done/pending/lectured`) with concept-map vocab (`mastered/current`).
- **Why / principle:** Visible structure cuts orientation cost and drives completion (Zeigarnik); LA-dashboard RCT: anchor progress to a goal benchmark, not isolated bars.
- **Where:** `agent.html` `.rbadge-*` (no `rbadge-lectured`; `rbadge-active` never fires) + `#route-list` Jinja (~189) and `updateGlass` (~390); fed by `trace.py:build_trace`.
- **Effort:** M. **Inspired by:** Coursera/Udemy lesson sidebar + MDPI LA-dashboard. **(closes the route-badge / "where am I" findings)**

---

## 3. Quick wins (<1hr each)

- **Add viewport meta to `agent_home.html`** (`<head>`, line 2) — copy from agent.html. The first screen on mobile is currently broken. *(blocker, trivial)*
- **Conditional cost label.** `agent.html` cost card hardcodes "(offline = $0)" even in live mode (captured 10101 tok ≈ $0.009). Show "Offline run — $0" when `tokens==0`, else the real spend. *(misleading panel)*
- **Move the goal form above the hero/pipeline on `agent_home.html`** — the only primary CTA is currently buried beneath ~5 explanatory blocks.
- **Add `<label>`/`aria-label` to both inputs** (home goal input line 67; tutor answer input line 165) — placeholder-only today.
- **Add `<h1>`** to `agent_home.html` (hero is `<h2>` with no `<h1>`; level skip).
- **Boundary label as real DOM, reworded.** Replace `.ai.boundary::before` CSS content (skipped by AT, jargon "OUTSIDE MY LITERATURE PACK") with a JS-injected `<span>` reading "Outside the papers I was given."
- **Remove/collapse the "Building your course…" card** once the first teach/question arrives — it persists above the lesson all session.
- **Header brand → link home** on both pages + a persistent "New session" link in the tutor header (currently only escape is the done-card).
- **Default the research-detail toggle OFF** for learner view (keep ON for judge mode); relabel "Agent flow / route v1" → "How the tutor decided."
- **`prefers-reduced-motion` guard** around `flash-in`/`vbump`/`.bar-fill` transitions (one `@media` block).

---

## 4. Bigger bets

- **Suggested follow-up chips** ("Quiz me", "I'm lost — explain differently", "Show the evidence", "Go deeper") under each teaching turn, POSTing the existing `answer`/`lost`/`aside` actions so learners don't need magic phrases. *(M — Apps SDK / ChatGPT follow-ups; dispatch layer already supports the actions)*
- **Interactive concept map.** Make `graph_svg.py` nodes clickable to jump ORIENT/TEACH to a concept (reuse route-replan) and collapse mastered prereq chains — turns a static diagram into the adaptive navigation lever. *(L — NotebookLM mind maps)*
- **Studio-style artifact rail / persistent Artifact tab** with one-click Study Guide / FAQ / Cornell notes / slides from mastered keypoints, each inheriting citation chips, with version history. `_artifact_event()` already yields format/url/citations/preview; promote it from a 600-char end-of-route preview to a pinned tab. *(M–L — NotebookLM Studio + Canvas/Artifacts)*
- **Progressive-disclosure mastery + confidence.** Encode confidence as the bar's graded/hatched extent (not a second identical bar), overlay a `mastery_threshold` tick, animate a +Δ on grade, and reveal contributing quiz turns on click. Directly surfaces the live-bug class where "bars stayed flat." *(L — uncertainty-viz (Wilke) + NotebookLM click-to-verify)*
- **Resume / momentum on `agent_home.html`** — a "Pick up where you left off: keypoint 4 of 9" card per in-progress goal + a subtle "concepts mastered this session" tally (honest, non-streak). *(M — Duolingo forgiveness, kept glass-box-honest)*
- **Full a11y pass** — `role="progressbar"` + `aria-valuenow` on bars, `aria-live="polite"` on `#thread`/`#working`, AA contrast fix on muted text (`#7a8699`, `#5b7494`, `.note`), `:focus-visible` rings, `aria-pressed`/`role="tab"` on the Chat/Glass toggle, resolve the mobile media-query vs toggle conflict. *(M — WCAG 2.2; table-stakes for a competition entry)*
- **Robust markdown renderer** — current `md()` drops headings/code/links and can mis-italicize a stray `*`; gpt-4o-mini routinely emits `##`/code. Adopt a small vetted lib or at least handle headings/code. *(M)*

---

## 5. Adopted-from-platforms table

| Idea | Source platform | Where in the code |
|---|---|---|
| Inline numbered citation chips → highlight source passage | Google NotebookLM | `agent.html` teach `handleEvent` + `md()`; `#evidence`; `current().cited` (266-271) |
| Honest "not grounded / no citations yet" empty states | NotebookLM + NN/g | `interactive.py current()` (274-281, 331-348); `agent.html` evidence/learner/cost cards |
| Persistent "grounded in N sources" strip + relevance gate | NotebookLM sources panel | `interactive.py _build_open_world` (359-406); `agent.html` header strip |
| Interactive mind-map nodes (click-to-scope, collapse) | NotebookLM mind maps | `graph_svg.py`; `#cmap` |
| One-click Studio artifact presets (Study Guide / FAQ / notes / slides) | NotebookLM Studio | `_artifact_event()` (116-144); `agent.html` right rail |
| Persistent lesson outline + status glyphs + progress bar | Coursera / Udemy | `agent.html` `#route-list` (189), `updateGlass` (390); `trace.py:build_trace` |
| "Knowledge Check · {Bloom}" framed quiz card | Udemy / Coursera | `agent.html` `.qa` (35), question branch (482) |
| Labeled "Recap — revisiting X" spaced-retrieval card | Coursera/Udemy review-signposting + Nature Rev Psych | `_STEP_LABELS` (60), question event (154); `agent.html` bubble |
| 3-tier named mastery chips (Familiar/Proficient/Mastered) | Khan Academy | presenter in `interactive.py current()`; `#learner` bars |
| Resume card + subtle session-momentum tally | Duolingo (with forgiveness) | `agent_home.html`; checkpoint/session DB |
| Honest, framed cost/effort meter (offline=$0 explicit, per-stage) | Coursera/Udemy effort estimates | `cost.py`; `agent.html` cost card (257-261) |
| Streaming "thinking trail" + Stop, staged build stepper | ChatGPT Canvas / Claude / NN/g | `agent.html` `#working`/step events; `streamEvents` abort |
| Suggested follow-up chips | OpenAI Apps SDK / ChatGPT | `agent.html` post-bubble; `AgentSession.handle()` actions |
| Plain-language XAI "why this next" + on-demand rule expander | ChatGPT/Claude + Eleken XAI | `flow_meta.py`/presenter; `agent.html` `#why` (243/428) |
| Confidence-as-graded-extent + Δ-on-change mastery bars | Wilke / arXiv 2508.00937 uncertainty-viz | `agent.html` `.bar-fill`/`.bar-c`, `updateGlass` learner loop |
| Persistent Artifact tab with version history | ChatGPT Canvas / Claude Artifacts | `_artifact_event()`; `/tutor/{sid}/artifact` |
| Inline error + Retry (no blind reload) | Canvas/Artifacts + NN/g error states | `agent.html` `streamEvents` catch / 'error' (489/504/545) |
| Designed empty/error states (92%/78% gap) | NN/g 2025 AI-dashboard review | all glass-box panels |
| Accessibility: progressbar/live-region/contrast/reduced-motion | WCAG 2.2 / WebAIM | `agent.html` `<style>`, `#thread`/`#working`, bars, toggles |
| Goal-benchmark progress + visible pacing | MDPI 2025 LA-dashboard RCT | `agent.html` route header; route/map data |
| Progressive disclosure (co-locate evidence with its claim) | LogRocket / Decision Lab; Duolingo/Slack | `agent.html` `md()` + `#evidence`; per-keypoint cite ids |

**Sequencing recommendation:** ship the two blockers (#1 feedback bubble, #2 DISCOVER gate) plus the §3 quick wins first — they convert the worst first-impression failures at the lowest cost — then #3/#4/#5 (empty states, plain rationale, quiz framing) which make the glass box finally *read* like a glass box, then the §4 bigger bets for the demo polish.