# LitNavigator — PPT Outline (ICCSE 2026)

**Target:** 10–12 slides  
**Every slide maps to at least one of the six official criteria.**  
**Six criteria (abbreviated):**  
1. Agentic — Agentic workflow & technical implementation  
2. Responsible AI — Responsible AI & trustworthiness  
3. Novelty — Novelty & innovation  
4. Usefulness — Practical usefulness  
5. Efficiency — Efficiency & cost-effectiveness  
6. Presentation — Presentation quality  

---

## Slide 1 — The Problem

**Title:** 30 Papers, Two Weeks — Who Teaches You?

**Bullets:**
- A researcher enters a new field: dozens of papers, no clear learning path
- Existing tools (Elicit, NotebookLM, Khanmigo) answer questions or summarize — none teach
- No adaptive curriculum, no misconception detection, no "what don't I know yet?"
- LitNavigator: an AI tutor that reads the literature and teaches through it

**Visual:** Split image — a pile of arXiv PDFs on the left; a confused learner on the right. Or a simple title card with the hook sentence.

**Criteria targeted:** Usefulness (6), Presentation (opening hook)

---

## Slide 2 — What Existing Tools Miss (Comparison Table)

**Title:** The Empty Square Nobody Fills

**Bullets:**
- Four tools compared: Elicit, NotebookLM, Khanmigo, LitNavigator
- Columns: Teaches adaptively | Detects misconceptions | Induces from your literature | Shows its reasoning | Honest when out of scope
- LitNavigator is the only tool with all five columns checked
- The "empty square" is personalized, literature-grounded, adaptive teaching

**Visual:** A 4-row × 5-column comparison table. Elicit/NotebookLM/Khanmigo have checkmarks in 1–2 columns only. LitNavigator row is fully checked. Highlight the "Induces from your literature" column — no other tool has it.

**Criteria targeted:** Novelty (3), Usefulness (4)

---

## Slide 3 — Architecture: Three Adaptive Loops

**Title:** A Real State Machine — Three Nested Loops

**Bullets:**
- Outer loop: Planner / Replan — builds and repairs the route (LangGraph state machine)
- Inner loop: Retrieve → Teach → Check → Grade → (Reteach | Advance | Concede | Induce)
- Induction loop: when a goal is off-skeleton, runs Induce Scaffold before teaching
- BKT (Bayesian Knowledge Tracing) tracks mastery per concept; rule-computed confidence
- Corpus: a pack of LLM-agent papers (evidence-only retrieval; no hand-curating new concepts needed)

**Visual:** A three-level flowchart: outer box = Plan/Replan; inner box = Teach/Check/Grade with four exit arrows (Advance, Reteach, Concede, Induce); small inset = Induction sub-graph. Annotate decision nodes.

**Criteria targeted:** Agentic (1), Responsible AI (2, shows traceability)

---

## Slide 4 — Money Shot 1: Adaptive Reteach (Misconception Detected)

**Title:** Misconception Caught Mid-Session — Strategy Switch

**Bullets:**
- Student types "ReAct is just chain-of-thought reasoning" — a known misconception
- System detects `react_is_just_cot`; switches from direct explanation to analogy strategy
- Mastery rises from 0.40 → ~0.80 after successful reteach
- Confidence is rule-computed from quiz evidence, not hallucinated
- All steps visible in the glass-box right panel in real time

**Visual:** Screenshot of the `/tutor` UI right panel showing:  
- "Why this step" field: "misconception detected: react_is_just_cot — switching strategy"  
- Mastery bar at 0.40 (before) and ~0.80 (after) — annotate both values with arrows  
- Confidence bar annotated as "rule-computed, not LLM-guessed"  
- Cited evidence chunk IDs (1–2 chunks highlighted)

**Criteria targeted:** Agentic (1), Usefulness (4), Responsible AI (2)

---

## Slide 5 — Money Shot 2: Adaptive Reroute (Missing Prerequisite)

**Title:** Wrong Prerequisite Detected — Route Replanned Automatically

**Bullets:**
- Student fails a quiz that reveals a missing prerequisite concept
- Agent inserts the prerequisite before the current concept in the route
- `route_version` increments from 1 → 2 — the route repair is visible and traceable
- Decision rationale cites the failed quiz and the prerequisite edge that was triggered
- No student action required: the agent repairs the plan silently

**Visual:** Screenshot of the `/sessions/<id>` panel (CLI-driven, agents corpus) showing:  
- Route BEFORE: `tool_use → react` (annotated "route_version: 1")  
- Route AFTER: `tool_use → <prereq_concept> → react` (annotated "route_version: 2")  
- "Why this step" field citing the failed quiz and edge insertion  
- Note in slide footer: "CLI demo — agents corpus fixture"

**Criteria targeted:** Agentic (1), Usefulness (4)

---

## Slide 6 — Money Shot 3: Literature-Induced Scaffolding (Core Novelty)

**Title:** The System Invents a Lesson from the Papers — Provenance Shown

**Bullets:**
- Goal: "multi-agent debate" — not in the curated syllabus
- System runs `planner → induce_scaffold`: reads the paper pack, induces the concept and its position
- Induced edge written: `multi_agent → multi_agent_debate`, `source='induced'`
- `confidence_basis` rule-computed: `{n_chunks, max_strength, multi_paper}` → e.g. 0.75
- Misconception mined: "more agents always helps" — labeled "contested" from evidence

**Visual:** Screenshot of the `/tutor` right panel showing:  
- Induced section with `source='induced'` annotated  
- `confidence_basis` JSON or structured display — annotate "rule-computed, not guessed"  
- Cited evidence chunk IDs for the induction  
- Concept label "contested" or "open" on the frontier concept  
- "Why this step" field confirming `induce_scaffold` path

**Criteria targeted:** Novelty (3), Responsible AI (2), Agentic (1)

---

## Slide 7 — Novelty: Intent Contrast (Same Corpus, Two Routes)

**Title:** One Engine, One Corpus — Two Completely Different Curricula

**Bullets:**
- Same LLM-agent paper pack; same underlying knowledge graph
- Researcher intent: deep prerequisite chain, methods, open problems — long route, high mastery target
- Journalist intent: landmark ideas, consensus/controversy map, short route — "can hold the conversation"
- Proof that the curriculum is re-scoped to purpose, not authored once
- Extensible: swap the paper pack → a tutor for any field

**Visual:** Side-by-side or stacked screenshot of two session panels showing the Route field:  
- Left/top: researcher route (long, annotated "6 concepts")  
- Right/bottom: journalist route (short, annotated "3 concepts")  
- Draw a bracket or arrow from "same corpus" to both routes

**Criteria targeted:** Novelty (3), Usefulness (4)

---

## Slide 8 — Responsible AI: Provenance, Confidence, and Honest Limits

**Title:** The Glass Box — Every Claim is Traceable

**Bullets:**
- Mastery and confidence are rule-computed (BKT + evidence rules) — not LLM-generated numbers
- Induced concepts carry `confidence_basis`: `{n_chunks, max_strength, multi_paper}` — auditable
- Evidence provenance: every teaching turn cites the exact chunk IDs from the paper pack
- Out-of-scope goals get an honest decline and a list of what *can* be taught
- Offline fallback: fully deterministic path, $0 cost — no black-box inference required

**Visual:** Screenshot of the right glass-box panel annotating four fields:  
1. Mastery/confidence bars — "rule-computed"  
2. Confidence_basis JSON — "auditable evidence formula"  
3. Cited evidence section — "chunk IDs → paper provenance"  
4. Honest decline response (from the "quantum chromodynamics" test) — "scope boundary enforced"

**Criteria targeted:** Responsible AI (2)

---

## Slide 9 — Efficiency & Cost: Cheap by Design, Shown on Screen

**Title:** Sub-Cent Sessions — Cost Visible Every Turn

**Bullets:**
- Model: gpt-4o-mini — fastest, cheapest OpenAI model for multi-turn teaching
- No vector database: SQLite cosine similarity (`sqlite-vss` or manual cosine) — zero infra cost
- Offline fallback: deterministic keyword router + fixture responses — $0.00, always available
- Cost panel (live in the UI): "This session: N tokens ≈ $0.00X; offline mode = $0"
- Token costs stored per turn in `tutor_turns.token_cost` — verifiable, not estimated post-hoc

**Visual:** Screenshot of the Cost so far panel showing token count and dollar figure. Annotate:  
- "$0.00X" for a live session  
- "$0.00" for offline mode  
- Small table: "gpt-4o-mini | SQLite | no vector DB | offline fallback"

**Criteria targeted:** Efficiency (5)

---

## Slide 10 — Limitations & Future Work

**Title:** What This System Does Not (Yet) Do

**Bullets:**
- Corpus is a curated LLM-agent paper pack (~8–30 papers); not arbitrary user upload (yet)
- New concepts require hand-authored edges/quizzes; expansion papers are evidence-only
- No cross-session persistence (each session starts fresh)
- Intent routing currently uses keyword fallback offline; LLM classification improves it
- Future: arbitrary paper upload, streaming UI, larger corpora, cross-session learner model

**Visual:** A two-column table: "Current" vs "Future roadmap" with 4–5 rows. Keep tone honest and forward-looking.

**Criteria targeted:** Responsible AI (2, honesty about scope), Presentation (6, judges appreciate candor)

---

## Slide 11 — Impact & Extensibility

**Title:** Point It at Any Paper Pack

**Bullets:**
- Architecture is domain-general: the teaching engine is decoupled from the corpus
- Swap the paper pack → a tutor for clinical trials, climate science, security research, law
- Competition instance: LLM-agent research; the engineering generalizes
- Corpus expansion is evidence-only (chunking + embedding + auto-tag) — no new authoring
- Lowers the cost of domain-expert tutoring to the cost of a paper pack

**Visual:** A diagram with the LitNavigator engine in the center and 4 domain "paper packs" radiating outward (agents, clinical, climate, security). Or a simple icon row.

**Criteria targeted:** Usefulness (4), Novelty (3)

---

## Slide 12 — Team & Close

**Title:** LitNavigator — Literature-Grounded Adaptive Tutoring

**Bullets:**
- [Team member names and roles]
- Built in 8 days on a clean LangGraph + FastAPI + SQLite stack (68+ tests, all green)
- Three adaptive loops: Plan/Replan → Teach/Check/Grade/Reteach → Induce
- Every decision traceable; every cost visible; every claim grounded in the literature
- Try it: `python -m litnav.ui.server` → `http://127.0.0.1:8000/tutor`

**Visual:** Final product screenshot showing the cohesive `/tutor` UI (left chat panel + right glass box). Include the GitHub repo URL or QR code if desired.

**Criteria targeted:** Presentation (6), all criteria summarized

---

## Six-criteria coverage check

| Criterion | Slides |
|---|---|
| 1. Agentic workflow & technical implementation | 3, 4, 5, 6 |
| 2. Responsible AI & trustworthiness | 3, 4, 6, 8, 10 |
| 3. Novelty & innovation | 2, 6, 7, 11 |
| 4. Practical usefulness | 1, 2, 4, 5, 7, 11 |
| 5. Efficiency & cost-effectiveness | 9 |
| 6. Presentation quality | 1, 10, 12 |

All six criteria are covered by at least one dedicated slide. Criteria 5 (Efficiency) is the narrowest — Slide 9 is fully dedicated to it and should be given adequate visual weight in the final deck.
