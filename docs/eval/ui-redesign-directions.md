I have a clear picture of the current UI. Now I'll write the redesign directions, grounded in both the research and the actual code (the `--accent:#5b49c4` purple, `storyband` gradient, `system-ui`, the 8-card flat glass-box stack, dual mastery/confidence bars, the `flash-in` yellow flash, `mode-chat`/`mode-glass` toggle, the SVG concept map).

---

# LitNavigator Tutor — Redesign Directions

The current UI is "engine strong, cockpit broken": a `system-ui` body, one purple accent (`#5b49c4`), a `linear-gradient` storyband, eight equal-weight flat cards in a side stack, and dual identical mastery/confidence bars. All three directions below retire those tells. They share one non-negotiable foundation (so they're comparable, not arbitrary), then diverge sharply on layout, palette, and signature interaction.

**Shared foundation (true of all three):** 4px spacing grid; numbers always in a tabular-figures monospace (mastery, confidence, cost, Bloom, paper counts); one fixed semantic color set (green=mastered, amber=conceded/boundary, neutral-gray=pending, accent=active) used identically across chat, route, map, and bars; motion strictly tied to real agent events (no decorative loops); citation chips inline in lesson prose linking to evidence; honest empty states on every panel. None of them use Inter + purple gradient + three-card rows.

---

## Direction A — "Calm Research Workspace"

**Vibe:** A quiet, paper-grounded reading room. Warm, editorial, low-key — it feels like reading a well-typeset journal that happens to teach you.

**Visual system**
- **Type:** Humanist serif for the *lesson prose and paper titles* (Source Serif 4 / Charter) — the "Google-Scholar-not-ChatGPT" read; clean grotesque (IBM Plex Sans) for glass-box chrome; IBM Plex Mono tabular for all numerals. The serif/sans split visually separates "the lesson" (warm) from "the machine" (cool).
- **Color:** Warm paper base `#FAF9F7`, ink `#1A1F29`, warm-gray ramp (reuse the existing `#4D5766`/`#7A8699`). ONE accent — desaturated teal `#0F6E66` — reserved only for citations + active state. Semantic amber `#B3700D` (already in the codebase as `--warn`) kept for boundary/conceded. Source quotes get a tinted-cream block (`#FFF8EC`, extending the existing `.ai.boundary` cream) with a left rule, so sourced text is visually separable from generated text.
- **Spacing/density:** Asymmetric by pane — chat is airy (16px/1.6 prose, 60–72ch measure), glass box is denser and table-like (it's for auditing). 8px grid. Cards lose the heavy `1px #e2e6ee` border + keep border-only OR a faint shadow, never both.
- **Motion:** Minimal. Line-by-line lesson streaming (Perplexity cadence); mastery fills animate on real grade only; citation-chip hover popover fades in ~120ms. Replace the `flash-in` yellow with a teal-tinted highlight that decays.

**Layout:** Keep the two-column chat | glass split but make it *coupled, not parallel*. The signature is **chat↔glass cross-highlight**: a citation chip in chat, an evidence card in the glass box, and a node on the map are the SAME object in three views — hover one, the others highlight. Glass box gets a density hierarchy instead of 8 equal cards: top zone (goal progress + current step + why) always visible, middle scrollable (route, map, evidence), Induced/Cost collapsed to a footer strip.

**Signature interactions**
1. Inline numbered citation chips bound to sentence-level claims → hover = exact-quote popover, click = highlight the evidence card.
2. Evidence-as-first-class cards: title · venue/year · the quoted span · a "used for: <keypoint>" line (Consensus/Elicit move).
3. Scroll-synced provenance: the active evidence card tracks the citation chip currently visible in the chat.
4. "Grounding strength" indicator per concept showing rule inputs (n papers, n keypoints) — surfaces *why* confidence is what it is, instead of a black-box number (honors "confidence is rule-computed").
5. Honest boundary state elevated into a designed amber "outside my literature pack" card, not an error.

**Inspired by:** Elicit, Consensus, Perplexity, Stripe microcopy.
**Cost:** Medium. Reuses the existing two-column shell and SVG; the heavy lifts are the type swap, the cross-highlight wiring, and the evidence-card upgrade.

---

## Direction B — "Living Glass-Box Instrument"

**Vibe:** A dark, precise cockpit that *reports its own thinking in real time*. The transparency is the product; the UI looks like an instrument panel built by engineers who respect you.

**Visual system**
- **Type:** Engineered, no serif. Geist Sans at a single ~510 body weight with negative tracking on display sizes; Geist/Berkeley Mono for every numeral and the agent-step labels. Strict ladder: 600 headings / 500 subheads / 400 body.
- **Color:** Dark-first, **4 surface levels by OKLCH lightness** (base L~11%, panel L~16%, nested/hover L~20%, overlay L~26%) — elevation by surface lightness, not shadow (shadows don't read on dark). Hairline borders ~8–10% lighter than their surface do the separation. ONE accent: amber-gold `#E0A33C` for active step / primary action / citations only; status green + conceded-amber fixed. This is the most dramatic break from the current flat light look.
- **Spacing/density:** Dense and orderly — 4px grid, 12px radii, container grouping over dividers, ~40–60% opacity on secondary text for free hierarchy.
- **Motion:** Diegetic and central. The working indicator IS the live step name ("Retrieving evidence…", "Grading your answer…") not a generic dot; the single active flow step pulses (replace the static `.step.active` background); the current concept-map node gets a gentle ring; mastery fills animate on real deltas.

**Layout:** **Glass-box-primary.** Flip the current default (`mode-chat`) — the instrument is the star, chat is a column within it. The signature is the **decision-trail timeline**: the agent flow (`setFlow()`) becomes a vertical, traceable timeline where each step shows plain name + state (done/active/pending) and expands to its inputs/evidence/output — a provenance log you can read backward. The existing research-detail chip folds into per-step expansion.

**Signature interactions**
1. Live named-step working trace that advances in lockstep with the streaming chat bubble (retrieve → ground → teach) — the two panes feel like one machine.
2. ⌘K command palette as the keyboard spine: jump to any route concept, switch mode, toggle research detail, hit cited evidence, start a new session, run a quiz. Replaces mousing the header toggle + checkbox.
3. **Confidence-as-uncertainty-band:** stop drawing two identical bars. Mastery = the fill; confidence = a translucent fuzzy band at the fill's leading edge (wide+fuzzy = tentative, crisp = confident), plus a one-word label. This is the literature's core uncertainty-viz move and kills the redundant dual-bar.
4. Expandable per-step provenance: click a flow step → its evidence + rule inputs + output.
5. Cost demoted to a quiet mono tabular footer ledger ("offline = $0" honesty).

**Inspired by:** Linear, Vercel/Geist, Stripe dark mode, agent-trace / provenance-log patterns, uncertainty-viz literature (Padilla/Kay/Hullman).
**Cost:** High. New dark surface system, the timeline rebuild, ⌘K, and the uncertainty-band bar are all real work.

---

## Direction C — "Focused Course-Player"

**Vibe:** A guided learning path with a clear "you are here." Friendly but serious — Duolingo/Khan discipline applied to grounded research, never gamified into dark patterns.

**Visual system**
- **Type:** One rounded-geometric display face for concept/section titles, a neutral grotesk for body, mono tabular for numbers. Lesson body 16px/1.5; section labels 13px uppercase tracked (extend the one good existing detail, `.storyk`).
- **Color:** Calm light base, ONE warm progress hue reserved exclusively for advancement, and a **3-tier mastery ramp readable by hue** (muted slate → teal → deep green) so tier is legible without reading the number. Conceded amber + boundary cream kept. No purple.
- **Spacing/density:** Establish hierarchy the current 8-card stack lacks — ONE hero element (the interactive path), secondary detail (evidence, rationale, prereqs) tucked behind node popovers. Generous vertical rhythm; ~64rem column.
- **Motion:** Tied to accomplishment only — mastery *tier* fills on advance, route node flashes to "done," subtle on-brand "agent working" state. No confetti-by-default.

**Layout:** **Three-zone — persistent left route rail | chat | contextual detail.** The route rail is the orienting spine the audit said was missing: the ordered concept journey as a single linear path with a strong "you are here" anchor and a jump-to-current control. The concept map and route *merge* into this one interactive path (node color = mastery tier, node icon = ORIENT/TEACH/ASSESS phase).

**Signature interactions**
1. Tap-a-node popover that consolidates the 3 scattered cards (evidence + why-this-step + prereqs) into on-demand contextual detail — click a path node to inspect it.
2. **Named mastery tiers over bare %** (Khan): Seen / Familiar / Solid / Mastered as a segmented tier meter, the % a quiet subscript; confidence demoted to a dot/tooltip. Legible pedagogy, not a raw model readout.
3. Quiz bubbles labeled "Knowledge Check · Bloom: Apply" with a guaranteed correct/incorrect feedback bubble explaining the *key idea* (not just advance/reteach routing).
4. Plain-language "why this next" as a guidance chip inline in the chat at each route change ("You stumbled on X, so we'll revisit prerequisite Y"); raw decision token stays in the glass box.
5. Follow-up affordance chips after a turn ("Quiz me" · "Why do I need this first?" · "Show the paper") mapped to real graph routes, reusing the existing `.storychip` pill.

**Inspired by:** Duolingo, Khan Academy, Brilliant, Arc sidebar.
**Cost:** High. Merging route+map into one interactive path and the three-zone restructure (from `.cols` two-column) are the big lifts; tiers and quiz framing are cheaper.

---

## Recommendation

**Lead with Direction B (Living Glass-Box Instrument), and pull two cheap, high-leverage moves from A and C into it.**

Why B: LitNavigator's *only* real differentiator from generic chat-AI is that it shows its work and grounds every claim — that's the competition's thesis. A "calm workspace" (A) is tasteful but under-sells the engine; a "course-player" (C) competes head-on with Duolingo/Khan on their turf where LitNav can't win on polish. B makes the transparency *the aesthetic*: the dark instrument surface, the live named-step trace, the decision-trail timeline, and the uncertainty-band bar all turn the "glass box" from a buried side-stack into the headline. It's also the strongest answer to the "cockpit broken" audit and the observed flat-bars bug (motion tied to real deltas surfaces it).

Adopt from the others to de-risk B's biggest weakness (it can read cold/engineer-only):
- From **A**: inline citation chips + evidence-as-cards + chat↔glass cross-highlight — the trust move, and it warms the instrument with real provenance.
- From **C**: named mastery tiers and the plain-language "why this next" guidance chip — keeps B human-legible so a learner, not just an engineer, can read it.

**Phasing to manage B's high cost:** Phase 1 (highest leverage, lower cost) — retire `#5b49c4`/the gradient/`system-ui`, ship the dark 4-surface system + type + semantic tokens + citation chips + named tiers + live named-step working indicator. Phase 2 — the decision-trail timeline, uncertainty-band bar, and ⌘K palette.

Relevant file: `/Users/jingyen/GitHub/LitNavigator/litnav/ui/templates/agent.html` (all styling, markup, and the `setFlow`/route/learner JS live here; `litnav/ui/graph_svg.py` renders the concept-map SVG; `litnav/ui/trace.py:build_trace` is the single data source the UI must read from).