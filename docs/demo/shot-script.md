# LitNavigator — Shot-by-Shot Video Script (ICCSE 2026)

**Total target runtime:** 3–5 minutes
**Recording surface:** local server at `http://127.0.0.1:8000`
**Corpus framing (say aloud in shot 1):** "Built from a pack of LLM-agent papers"
Do NOT claim production-scale or fully-autonomous-from-arbitrary-papers.

> **Updated 2026-06-20 for the ORIENT→TEACH→ASSESS demo form.** The old "reactive
> missing-prerequisite reroute" Money Shot (route_version 1→2 via diagnose→replan) is **removed**:
> the planner now expands the full prerequisite closure UP FRONT, so prerequisites are taught
> **proactively** (the ORIENT roadmap), not inserted after a stumble — `demo-reroute` now *concedes*,
> it does not replan. The new headline adaptive beat is **ORIENT** (shot 2). The reactive
> replan path still exists for **induced** off-skeleton concepts (shot 5).

---

## Pre-recording setup

```bash
# Terminal 1 — start the UI server (keep running throughout)
python -m litnav.ui.server
```

Open `http://127.0.0.1:8000/tutor` before recording. The page should show the **story band**
(Discover / Digest / Representative-5) across the top.

---

## Shot 0 — The Problem Hook (~10s)

**Surface:** Title card / greyed-out PDF thumbnails.
**Narration:** "Thirty agent papers land in two weeks. Who maps the prerequisite chain, walks you
through it, adapts when you stumble, and tells you what it doesn't know?"

---

## Shot 1 — DISCOVER + DIGEST: the offline pipeline made visible (~25s)

**Surface:** `/tutor` home/agent page — the **story band** at the top.

**On-screen action:** Hold on the story band; cursor-highlight each cell.

**Narration:**
> "First the pipeline. LitNavigator collected the agent papers offline, then *digested* them into a
> concept map — concepts, prerequisites, key points, all grounded in the literature. This map is the
> spine everything else runs on."

**Point at (story band):**
- **Discover** cell — the domain + "**N papers were collected offline for this domain**".
- **Digest** cell — "**N-concept map**" + the concept chips.
- **Representative 5** cell — the 5 representative paper titles.

**Say honestly:** the discover/digest step is pre-run offline (the pipeline really calls arXiv; here
it's cached). Teaching is live.

---

## Shot 2 — ORIENT: the roadmap fly-over (NEW headline) (~30s)

**Surface:** Live `/tutor` — free-text goal entry, then the ORIENT roadmap message.

**On-screen action:**
1. In the goal box, type: `I want to understand multi-agent collaboration`
2. Submit. The agent opens with an **ORIENT roadmap** message (not a quiz yet).

**Narration:**
> "Give it a goal. Before teaching anything, the agent lays out the *roadmap* — it pulls in the
> prerequisites this concept depends on and orders them, then says 'we'll start here.' You see the
> whole path before you walk it, so you never hit a wall you can't explain."

**Point at:**
- The **ORIENT message** in chat — the ordered concept list ("1. … 2. … we'll start with **X**"),
  with prerequisites appearing **before** the target.
- **Glass box → Concept map** — the same path lit up (current node highlighted; prereq → target
  edges). **Glass box → Learning route** — prerequisites front-loaded ahead of the target.

> This replaces the old reactive reroute: adaptivity here is **proactive sequencing**, not
> after-the-fact insertion.

---

## Shot 3 — TEACH / ASSESS: per-keypoint adaptive teaching (~60s)

**Surface:** Live `/tutor`, continuing the session.

**On-screen action:**
1. Let the agent teach the first concept **key point by key point** (grounded, with a `(Source: chunk …)` citation).
2. When the quiz appears, type a **wrong answer**. Watch it **reteach with a different strategy**
   (analogy / worked example) and re-ask.
3. Type the **correct answer** → it advances; mastery rises.
4. (Optional) type `I'm lost` mid-concept → the agent **backs up and re-explains more simply** (the
   "I don't understand" intent), without grading it as an answer.

**Narration:**
> "Teaching is live and grounded — every explanation cites the paper chunk it came from. Answer
> wrong and it doesn't repeat itself; it switches strategy and re-asks. Mastery is tracked from your
> actual answers, not guessed by the model. Say 'I'm lost' and it backs up."

**Point at (Glass box):**
- **Cited evidence** — the chunk IDs grounding the explanation.
- **Learner model** — the mastery / confidence bars moving after answers.
- **Agent flow** — `teach_kp → assess → grade → …` lighting up; the route node recoloring on the map.

**Counterfactual (brief):** answer correctly first time → advances with no reteach.

---

## Shot 4 — Literature-Induced Scaffolding (Novelty Core) (~45s)

**Surface:** Live `/tutor` — new session.

**On-screen action:**
1. Goal box: `multi-agent debate` (or `I keep seeing multi-agent debate — where does it fit?`)
2. Submit; wait for the right panel.

**Narration:**
> "Multi-agent debate isn't in the curated syllabus. Instead of refusing, the agent reads the paper
> pack in real time — *inducing* the concept, a prerequisite edge into the existing graph, and even a
> misconception the literature flags. Confidence is rule-computed from the evidence, not guessed."

**Point at:**
- **Induced** panel / map — the induced concept and its `source='induced'` edge (dashed on the map).
- **`confidence_basis`** — e.g. `{n_chunks, max_strength, multi_paper}` → computed confidence (e.g. 0.75).
- **Cited evidence** — the chunks that grounded the induction.
- Frontier label ("contested"/"open") if shown — "it labels the frontier honestly."

> This is also where the **reactive replan** still lives: an induced concept's prerequisite is woven
> into the route (`route_version` ticks). *Verify live before relying on it as an on-camera beat.*

---

## Shot 5 — Intent Contrast (Same Corpus, Different Routes) (~25s)

**Surface:** `/tutor` home intent links, Glass-box view.

**On-screen action:** Start **Researcher** (`/tutor/start?intent=researcher`) → Glass box → long route,
`mode: researcher (depth explain, bar 0.8)`. Then **Journalist** (`?intent=journalist`) → short,
frontier-first route, `mode: journalist (depth recall, bar 0.6)`. Cut between them.

**Narration:**
> "Same paper pack, two purposes. A researcher gets the full prerequisite chain at a high bar; a
> journalist gets a short, frontier-first route. One engine, one corpus, two curricula."

**Off-camera check:** `python -m litnav.app demo-intent` prints both routes to confirm before recording.

---

## Shot 6 — Responsible AI: honest boundary + cost (~25s)

**Beat 6a — honest boundary bridge (Surface: `/tutor`).**
1. Type a clearly out-of-corpus learn request: `teach me linear algebra first`
2. Submit. The agent gives a **graceful, honest boundary reply** (amber bubble): it names the
   out-of-scope topic, says it's outside the literature pack, and **declines to fake-teach it** —
   rather than a flat one-line refusal.

> Narration: "Ask for something outside its literature and it's honest about the edge of what it
> knows — it names the gap and refuses to bluff, instead of pretending."

Point at the **boundary (amber) reply** and read the rendered text aloud.

**Beat 6b — cost panel (Surface: any active session, Glass box).**
Point at the **Cost so far** panel — tokens + estimated USD.
> Narration: "Every session meters tokens and spend — gpt-4o-mini, fractions of a cent. Offline with
> no key it's $0; the deterministic fallback still teaches."

---

## Shot 7 — Close: Value Prop + Extensibility (~15s)

**Narration:**
> "LitNavigator is domain-general. Point it at any paper pack — clinical trials, climate models,
> security research — and it digests the literature into a map, walks you through it, adapts to each
> learner, and never teaches beyond what the papers support."

---

## Recording checklist

- [ ] Shot 0: hook card / PDF thumbnails
- [ ] Shot 1: story band — Discover (N papers) / Digest (N-concept map) / Representative-5
- [ ] Shot 2: goal → **ORIENT roadmap** (prereqs ordered before target) + concept map / route panel
- [ ] Shot 3: per-keypoint teach (cited) → wrong → reteach (new strategy) → correct → mastery rises (+ "I'm lost")
- [ ] Shot 4: `multi-agent debate` → induced edge + `source='induced'` + confidence_basis + cited chunks
- [ ] Shot 5: intent links (researcher vs journalist) → Glass box → different routes, same corpus
- [ ] Shot 6a: `teach me linear algebra first` → honest **boundary bridge** (amber)
- [ ] Shot 6b: active session → Glass box → Cost so far panel
- [ ] Shot 7: closing narration

## Six-criteria coverage (shots)

| Criterion | Covered by shot(s) |
|---|---|
| Agentic workflow & technical implementation | 2 (ORIENT proactive sequencing), 3 (per-keypoint teach/assess + reteach), 4 (induce_scaffold) |
| Responsible AI & trustworthiness | 3 (grounded citations, evidence-based mastery), 4 (provenance, confidence_basis), 6a (honest boundary), 6b ($0 offline) |
| Novelty & innovation | 1 (literature digest → map), 4 (live induction), 5 (intent contrast) |
| Practical usefulness | 2 (roadmap on-ramp), 3 (adaptive teaching + "I'm lost"), 7 (extensibility) |
| Efficiency & cost-effectiveness | 6b (cost panel, offline=$0, gpt-4o-mini) |
| Presentation quality | 1 (story band), 0/7 (hook + close) — all shots contribute |

> **Removed vs the prior script:** the standalone "missing-prerequisite reroute" shot
> (`demo-reroute`, route_version 1→2). Under the full-prereq-closure planner that path no longer
> fires for in-corpus prerequisites (it concedes); proactive ORIENT sequencing (shot 2) is the
> replacement. Reactive replan survives only for induced concepts (shot 4).
