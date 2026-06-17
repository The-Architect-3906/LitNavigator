# LitNavigator — Competition Push Design (ICCSE 2026 Agentic AI)

- **Date:** 2026-06-17
- **Status:** Design (approved in brainstorming; pending spec review)
- **Submission deadline:** 2026-06-25 (video + PPT to Tianchi). Registration: **done.**
- **Baseline commit:** `79b1831` (68 tests + G0–G3 green offline; working tree clean)

## 1. Context & Goal

LitNavigator is a stateful AI tutor built from and teaching through the living research
literature. The gated core (M0–M3) is complete and verifiable: a real LangGraph state
machine with planning, retrieval, adaptive routing (reteach / replan / concede / induce),
BKT mastery, rule-computed confidence, and literature-induced scaffolding with provenance.

The competition judges a **demo video + PPT report** against six criteria (below). The
engineering criteria are already strong; the criteria that decide ranking — practical
usefulness, novelty of interaction, *demonstrated* cost-efficiency, and presentation — are
where points remain. This design covers BOTH the product changes and the deliverable, with
8 days to submission, under a **presentation-first** posture (protect video/PPT time).

A previously-built free-text prototype was reverted at the user's instruction; the frontend
work described here is **not-started** and tracked as such.

## 2. Official Criteria → Current Standing

| Criterion | Standing | Why |
|---|---|---|
| Agentic workflow & technical impl. | 🟢 Strong | Real state machine: planning, retrieval, multi-step reasoning, adaptive routing, progress monitoring (BKT) |
| Responsible AI & trustworthiness | 🟢 Strong | mastery/confidence rule-computed (not LLM-guessed); induced provenance + evidence; honest concede; offline fallback |
| Novelty & innovation | 🟡 Med-high | Strong scenario/workflow novelty (syllabus induced from papers); interaction currently reads as preset/scripted |
| Practical usefulness | 🟡 Med | Real adaptivity, but vertical slice: preset entry, 8-paper corpus, no free goal |
| Efficiency & cost-effectiveness | 🟡 Med | Cheap by design (gpt-4o-mini, offline fallback, no vector DB) — but **not demonstrated** anywhere visible |
| Presentation quality | 🔴 Not started | No video/PPT yet — an explicitly weighted criterion |

## 3. Locked Decisions (from brainstorming)

1. **Scope of this plan:** product changes **and** deliverable, prioritized over 8 days.
2. **Main persona:** transitioning researcher/engineer entering "LLM agents." Journalist
   intent is the **novelty-contrast** beat (same corpus, re-scoped) — shown, not the spine.
3. **Product depth:** free-text goal entry **and** a visible cost panel — both folded into
   a frontend rework (below).
4. **Frontend ambition:** a **cohesive single-page product UI** (left: chat-style
   interaction; right: live route + learner state + evidence + cost). Keep the existing
   FastAPI + Jinja backend and trace layer; rework only the presentation layer. **No SPA
   framework** (risk control). Replaces the current bare-HTML panels.
5. **Corpus:** expand to ~25–30 agent papers, **evidence/retrieval only** (extract chunks +
   embeddings + auto-tag to nearest existing concept). The curated 7-concept teachable spine
   and the induction candidate stay fixed (money shots unchanged).
6. **Deliverable from me:** shot-by-shot video script + page-by-page PPT outline (team
   records / renders).
7. **8-day posture:** Approach A (presentation-first); hard product freeze ~D3.

## 4. Product Design

### 4.1 Cohesive product UI (the main frontend work)
One page, server-rendered (Jinja template + CSS, minimal vanilla JS for submit/poll):
- **Left — conversation:** a free-text goal box at the top; below it the running transcript
  of teaching turns and quiz questions; an answer box that posts back and the page updates
  (interrupt/resume already exists via `TutorSession`).
- **Right — live agent state (the "glass box"):** current route + `route_version`; the
  learner model (mastery / confidence as separate bars; three-color concept strip
  consensus/contested/open); cited evidence chunks (clickable); decision rationale;
  curated-vs-induced provenance with `confidence_basis`; the **cost panel** (§4.3).
- **Header:** explicit corpus scope line — "Built from N LLM-agent papers; ask within this
  scope" — so the boundary is intentional and visible.
- Reuses `build_trace()` for the right-hand data; the left side reuses `TutorSession`.
- **Maps to:** Novelty (interaction), Practical Usefulness, Presentation (on-camera
  credibility), Responsible AI (the glass box itself).

### 4.2 Free-text goal resolver
New `litnav/goal.py :: resolve_goal(goal_text, concepts, off_skeleton)` → one of:
- `concept` → plan a route to a curated concept and teach it;
- `induce` → the goal names an off-skeleton concept (e.g. multi-agent debate) → induce its
  scaffold from the papers, then teach;
- `unknown` → not in this corpus → honest reply listing what *can* be taught.

LLM-classifies when a provider is set; **deterministic keyword fallback offline**. The
returned slug is **validated against the candidate set** (a hallucinated slug can never
start a bogus session). Routed through `agents_m3.json` (all 7 concepts + induction
candidate). Replaces the preset `mode=react|induce` buttons.

### 4.3 Cost / efficiency panel
Sum `tutor_turns.token_cost` (already stored) per session → total tokens; estimate ≈ $X at
gpt-4o-mini pricing (a single blended-rate constant); display "this session: N tokens ≈ $X;
offline mode = $0." Surfaces the efficiency story a judge currently cannot see.
**Maps to:** Efficiency & Cost-effectiveness.

### 4.4 Corpus expansion (evidence-only)
New evidence-only ingest path: source ~20 more LLM-agent papers (team-provided or fetched
by arXiv id list), extract + chunk + embed, **auto-tag each chunk to its nearest existing
concept** (embedding similarity) — no new hand-authored concepts/edges/quizzes. Rebuild the
vector index. Enriches grounded teaching + induction evidence and makes the "~30 papers"
claim true. The curated spine and money shots are untouched.
**Maps to:** Practical Usefulness; supports the induction/retrieval narrative.

### 4.5 Recast the reroute money shot onto the agent corpus
Today the missing-prerequisite reroute (Money Shot 1) runs on the RAG fixture, not the
agent corpus. To keep the video's main thread entirely in the agents domain, introduce a
prerequisite gap within the agent route so the reroute demos on agents. **Fallback:** if
recast is risky, the video does a brief labeled scene-switch and explains it.

### 4.6 Out-of-domain behavior (trust feature)
Out-of-corpus goals get an honest decline + coverage list (via `resolve_goal` → `unknown`).
This is positioned as a feature: LitNavigator only teaches what the literature supports and
will not fake expertise. Architecture is domain-general (swap the paper pack → a tutor for
that field); the demo instance's corpus is LLM agents.
**Maps to:** Responsible AI (transparency, limitations).

### 4.7 Out of scope (YAGNI for this push)
Arbitrary user paper upload; new hand-curated concepts for expansion papers; cross-session
persistence; streaming text; SPA framework. None are required for the deliverable.

## 5. Deliverable Design

### 5.1 Video (~3–5 min) — researcher main thread + journalist contrast
| Shot | Content | Criterion |
|---|---|---|
| 0 Problem (10s) | "30 agent papers, two weeks — who teaches you?" | Usefulness |
| 1 Free-text goal | Type a goal → agent plans a route from the papers ("Built from ~30 papers") | Novelty / Usefulness |
| 2 Reteach | ReAct=CoT → misconception detected → strategy switch → mastery 0.40→0.80, calibrated confidence | Agentic / Usefulness |
| 3 Reroute | Wrong prerequisite → `route_version`+1 → prereq inserted (on agents, §4.5) | Agentic |
| 4 Induction | Type "multi-agent debate" → off-skeleton → induce edge+misconception, show `source='induced'` + `confidence_basis` + evidence | **Novelty (core)** |
| 5 Innovation reveal | Same corpus, switch to journalist intent → a completely different short route | **Novelty** |
| 6 Trust + cost | Out-of-domain honest decline + cost panel ("whole session ≈ $0.00X; offline $0") | Responsible AI / Efficiency |
| 7 Close | Value prop + extensibility ("point it at any paper pack") | Presentation |

### 5.2 PPT (~10–12 slides)
Problem → the "empty-square" comparison table → architecture (three loops) → 3 money-shot
slides (each a trace screenshot with annotated fields) → novelty (intent contrast) →
Responsible AI (provenance / confidence / concede / honest decline) → Efficiency (cost
numbers, offline fallback, no vector DB) → limitations & future → impact & extensibility →
team / close. **Every slide maps to one of the six criteria** (coverage check at D6).

## 6. 8-Day Timeline (revised for cohesive UI)

| Day | Product track (me) | Deliverable track | Gate / checkpoint |
|---|---|---|---|
| D0 6/17 | Spec finalized; prototype reverted (not-started) | — | working tree clean @ 79b1831 |
| D1 6/18 | `goal.py` resolver + cohesive UI skeleton (left chat / right panels) + free-text wired | Draft v1 shot script (beats) so team can pre-plan | pytest + 4 gates green; live smoke |
| D2 6/19 | Finish UI (cost panel, learner-state viz, provenance, scope header, styling) | Team pre-plans recording | tests/gates green |
| D3 6/20 | Corpus expansion (evidence-only) + recast reroute; verify all money shots on agents live | — | **PRODUCT FREEZE (EOD)** |
| D4 6/21 | bug-fix only | PPT page-by-page outline; refine shot script with exact trace fields; team first recordings | — |
| D5 6/22 | bug-fix only | Team records money shots; narration + on-screen annotations; full live dry-run | — |
| D6 6/23 | — | Edit video; finalize PPT; **6-criteria coverage review** | each criterion has a visible moment |
| D7 6/24 | — | Re-record weak shots; compress; English pass | — |
| D8 6/25 | — | Buffer + submit with margin | submitted |

Parallelization (3-person team): shot script lands D1 so members can plan; but recording of
the real UI happens after the D3 freeze, compressing recording+edit into D4–D7.

## 7. Risks & Fallbacks

- **Cohesive UI overruns into video time** → keep it server-rendered Jinja+CSS (no SPA);
  if behind, ship §4.1 left+right minimally and style later.
- **Cannot source ~20 PDFs** → keep 8 papers; reframe as "competition paper pack" (corpus
  expansion is a declared de-scopable item).
- **Live LLM flakiness during recording** → record on the offline deterministic path (teach
  still valid; cost panel then shows $0).
- **Reroute recast on agents is risky** → labeled scene-switch in the video (§4.5 fallback).
- **Product freeze slips past D3** → cut corpus expansion first, then reroute recast; never
  cut the video buffer below D7.

## 8. Testing & Gates

- Every product task keeps `pytest` (currently 68) + G0–G3 green **offline** (provider=none).
- New tests: `resolve_goal` (concept / induce / unknown / empty / hallucinated-slug);
  cost-panel sum correctness; evidence-only ingest auto-tag; reroute-on-agents gate path.
- Live smoke after each LLM-touching change (provider=openai), no key in any commit.
- Follow the established commit → `push origin HEAD:main` → ff local main → verify three
  refs flow.

## 9. Deferred to the implementation plan

- Exact UI layout/markup and CSS approach.
- The arXiv id list for corpus expansion (and whether team supplies PDFs).
- Whether reroute is recast on agents or handled by scene-switch.
- gpt-4o-mini blended price constant for the cost estimate.
