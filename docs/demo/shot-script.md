# LitNavigator — Shot-by-Shot Video Script (ICCSE 2026)

**Total target runtime:** 3–5 minutes  
**Recording surface:** local server at `http://127.0.0.1:8000`  
**Corpus framing (say this aloud in shot 1):** "Built from a pack of LLM-agent papers"  
Do NOT claim production-scale or fully-autonomous-from-arbitrary-papers.

---

## Pre-recording setup

```bash
# Terminal 1 — start the UI server (keep running throughout)
cd <project-root>
python -m litnav.ui.server

# Terminal 2 — run CLI demos as each shot requires (see per-shot instructions)
```

Open browser to `http://127.0.0.1:8000/tutor` before recording begins.

---

## Shot 0 — The Problem Hook (~10 seconds)

**Surface:** Title card / screen with no browser visible (optional: a pile of PDF thumbnails or the browser tab sitting idle).

**On-screen action:** No interaction. Hold a static image or show 30 greyed-out paper thumbnails.

**Narration:**
> "Thirty agent papers land in two weeks. Who teaches you the prerequisite chain, adapts when you get it wrong, and tells you what it doesn't know?"

**Point at:** Nothing — this is a verbal hook only.

**Counterfactual:** N/A

---

## Shot 1 — Free-Text Goal Entry (~20 seconds)

**Surface:** Live `/tutor` UI — the free-text goal box at the top of the left panel.

**On-screen action:**
1. Click the goal text box (the input field labelled something like "What do you want to learn?").
2. Type exactly:
   ```
   I want to understand ReAct
   ```
3. Submit (press Enter or click the Send/Start button).
4. Wait for the right panel to populate (2–5 seconds).

**Narration:**
> "Type a free-form learning goal. LitNavigator reads the LLM-agent paper pack and plans a route — no dropdown, no preset mode."

**Point at (right panel after submission):**
- The **Route** field — it shows a sequence of concepts (e.g. `llm_agents → tool_use → react`).
- The **route_version** counter — confirm it reads `1`.
- The corpus scope header line ("Built from N LLM-agent papers; ask within this scope") visible at the top of the page.

**Counterfactual:** N/A for this shot.

---

## Shot 2 — Reteach on Misconception (Mastery Rise) (~60 seconds)

**Surface:** Live `/tutor` UI — continuing the session from Shot 1, OR start a fresh `/tutor` session and re-type the ReAct goal.

**On-screen action:**
1. Read the teaching explanation aloud or let it render on screen.
2. When the quiz question appears, type the **wrong answer** into the answer box:
   ```
   it just uses chain of thought reasoning
   ```
3. Submit the answer.
4. Watch the right panel update.
5. Read the reteach explanation (the agent switches to an analogy strategy).
6. When the follow-up quiz appears, type the **correct answer**:
   ```
   the agent takes actions and observations
   ```
7. Submit.

**Narration (after wrong answer):**
> "The system detects the misconception — ReAct-is-just-CoT — and switches teaching strategy from direct explanation to analogy, without the student asking for help."

**Narration (after correct answer):**
> "After reteaching, mastery rises from 0.40 to roughly 0.80. Confidence is rule-computed from quiz evidence, not guessed by the LLM."

**Point at (right panel, highlight with cursor after each step):**
- After wrong answer: the **"Why this step"** field — it should read something like "misconception detected: react_is_just_cot — switching to analogy strategy".
- The **Learner model** section — point at the **mastery bar** showing the current value (~0.40) and the **confidence bar**.
- After correct answer: point at the mastery bar again — watch it rise to ~0.80.
- The **Cited evidence** field — show 1–2 chunk IDs cited for the reteach explanation.

**Counterfactual (brief cut, ~10 seconds):**
> "If the student had answered correctly the first time — [type correct answer from the start] — the route advances directly without reteaching."

*(Record this separately and cut it in as a quick branch.)*

---

## Shot 3 — Missing-Prerequisite Reroute (route_version bump) (~30 seconds)

**Surface:** CLI runner + `/sessions/<id>` panel — NOT the free-text `/tutor` UI.  
**TEAM NOTE:** This shot uses a fixture (`data/seed/agents_reroute.json`) gated by `tests/test_reroute_agents.py`. It is NOT yet wired to the free-text UI. Record it as a separate CLI-driven segment and label it clearly in the video (e.g. a title card: "Adaptive Rerouting — Agent Corpus").

**On-screen action:**
1. In Terminal 2, run:
   ```bash
   python -m litnav.app demo-reroute
   ```
   *(Runs the `data/seed/agents_reroute.json` fixture: a wrong answer reveals a missing prerequisite (`tool_use` for `reflection`), so `replan` inserts it and `route_version` goes 1 → 2 — all on the agent corpus.)*
2. After it completes, open the browser to the session panel:
   ```
   http://127.0.0.1:8000/sessions/<id>
   ```
   (The server will show the most-recent session or you can copy the session ID from the CLI output.)

**Narration:**
> "When a quiz reveals the student is missing a prerequisite, the agent replans — it inserts the missing concept before the current one, and route_version ticks up. The student never hits a wall they can't explain."

**Point at (right panel / sessions panel):**
- The **Route** field — show the route BEFORE (e.g. `tool_use → react`) vs AFTER (e.g. `tool_use → <prereq_concept> → react`).
- The **route_version** counter — highlight it changing from `1` to `2`.
- The **"Why this step"** / decision rationale — confirm it references the failed quiz and the inserted prerequisite edge.

**Counterfactual (brief):**
```bash
python -m litnav.app demo-m2 --answer correct
```
> "Correct answer: route_version stays at 1, no replan needed."

---

## Shot 4 — Literature-Induced Scaffolding (Novelty Core) (~50 seconds)

**Surface:** Live `/tutor` UI — start a new session.

**On-screen action:**
1. In the goal box, type:
   ```
   multi-agent debate
   ```
   (or the fuller phrase: `I keep seeing multi-agent debate. Where does it fit?`)
2. Submit.
3. Wait for the right panel to populate.

**Narration:**
> "Multi-agent debate is not in the curated syllabus. Instead of refusing, the system reads the paper pack in real time — inducing the concept, its position in the graph, and even a misconception the literature flags."

**Point at (right panel):**
- The **Induced** section (or the Route showing `multi_agent → multi_agent_debate`) — highlight `source='induced'`.
- The **`confidence_basis`** field — e.g. `{n_chunks: 1, max_strength: explicit_assertion, multi_paper: false}` → computed confidence 0.75. Point out: "This is rule-computed from the evidence, not an LLM guess."
- The **Cited evidence** chunks — show the chunk IDs that grounded the induction.
- The concept label — if it reads "contested" or "open", point to it and say "the system labels the frontier honestly."
- The **"Why this step"** rationale confirming the `induce_scaffold` path was taken.

**Counterfactual:** N/A (the contrast is the curated-vs-induced distinction visible in the same panel).

---

## Shot 5 — Intent Contrast (Same Corpus, Different Routes) (~30 seconds)

**Surface:** CLI runner + split-screen or sequential browser panels.

**On-screen action:**
```bash
python -m litnav.app demo-intent
```
This runs two sessions back-to-back (researcher intent and journalist intent) against the same agent paper corpus.

Open the two session panels in the browser:
```
http://127.0.0.1:8000/sessions/<researcher-id>
http://127.0.0.1:8000/sessions/<journalist-id>
```
Show them side-by-side or cut between them.

**Narration:**
> "Same paper pack, two purposes. A researcher gets the full prerequisite chain — methods, open problems, high mastery bar. A journalist gets a short high-level route — landmark ideas, consensus vs controversy. One engine, one corpus, two completely different curricula."

**Point at:**
- The **Route** field in each panel — the researcher route is long with deep prerequisites; the journalist route is short and concept-map-style.
- The **Learner model** section — note how the mastery/confidence targets differ between intents.

---

## Shot 6 — Responsible AI: Honest Decline + Cost Panel (~25 seconds)

**Surface:** Live `/tutor` UI.

**On-screen action:**
1. Start a new session.
2. In the goal box, type:
   ```
   teach me quantum chromodynamics
   ```
3. Submit and let the response render.
4. Then (without clearing the page) pan or scroll to show the **Cost so far** panel on the right.

**Narration (on the decline response):**
> "Out of scope — the system says so clearly. LitNavigator only teaches what the literature it was built from actually supports. It does not fake expertise."

**Narration (on the cost panel):**
> "The cost panel shows tokens used and estimated spend. Run offline with no API key and it's zero dollars — the deterministic fallback still teaches."

**Point at:**
- The honest decline message in the left panel — it should list what CAN be taught ("Here are the concepts available in this corpus:").
- The **Cost so far** panel on the right — highlight the token count and the dollar estimate. If recording offline, point to the "$0.00" and say "offline mode."

---

## Shot 7 — Close: Value Prop + Extensibility (~15 seconds)

**Surface:** Live `/tutor` UI showing the goal box (clean/empty state).

**On-screen action:** No interaction — hold the UI on screen while narrating.

**Narration:**
> "LitNavigator is domain-general. Point it at any paper pack — clinical trials, climate models, security research — and it builds the curriculum from the literature, adapts to each learner, and never teaches beyond what the papers support."

**Point at:** The corpus scope header line. Optionally briefly show the goal box to imply open-ended reuse.

---

## Recording checklist

- [ ] Shot 0: static hook card or PDF thumbnails
- [ ] Shot 1: goal box → type "I want to understand ReAct" → right panel populates (route + route_version=1)
- [ ] Shot 2: wrong answer → misconception detected → reteach → mastery 0.40→~0.80 (+ counterfactual cut)
- [ ] Shot 3: CLI `demo-reroute` → sessions panel → route_version 1→2 (+ counterfactual cut)
- [ ] Shot 4: goal "multi-agent debate" → induced edge + source='induced' + confidence_basis + cited chunks
- [ ] Shot 5: `demo-intent` → two session panels → different routes same corpus
- [ ] Shot 6: "teach me quantum chromodynamics" → honest decline + cost panel
- [ ] Shot 7: closing narration on clean UI

## Six-criteria coverage (shots)

| Criterion | Covered by shot(s) |
|---|---|
| Agentic workflow & technical implementation | 2 (reteach loop), 3 (replan loop), 4 (induce_scaffold path) |
| Responsible AI & trustworthiness | 2 (rule-computed confidence), 4 (provenance, confidence_basis), 6 (honest decline, $0 offline) |
| Novelty & innovation | 1 (free-text goal), 4 (induction), 5 (intent contrast) |
| Practical usefulness | 1 (free-text entry), 2 (adaptive teaching), 7 (extensibility) |
| Efficiency & cost-effectiveness | 6 (cost panel, offline=$0, gpt-4o-mini) |
| Presentation quality | 0 (hook), 7 (close) — all shots contribute to overall polish |
