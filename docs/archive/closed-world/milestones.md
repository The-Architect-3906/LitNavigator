# Milestones

LitNavigator is built as a risk ladder. Each milestone must be runnable, recordable, and verifiable before the next milestone starts.

## Milestone Rule

Do not advance past a gate that has not passed. A polished lower milestone is better than an unstable higher milestone.

> **Gates are serial; the work inside each milestone is parallel.** Three tracks (A data, B engine, C UI+eval) run concurrently and converge at each gate. (M0–M3 have shipped; the original layer-by-layer engineering plan has been archived and removed — the code + gates are the source of truth.)

## M0: Fake-Data Walking Skeleton

**Goal:** prove the software loop and durable trace exist.

**Build:**

- Python package skeleton.
- deterministic seed fixture.
- SQLite schema for core tables.
- simple route planner.
- fixed quiz.
- BKT-lite mastery/confidence update.
- decision logging.
- `verify_m0` command.

**Gate G0:**

- session row exists,
- route rows exist,
- learner state changes,
- quiz attempt is written,
- decision is written,
- no network access is needed.

**Command:**

```bash
python -m litnav.evaluation.verify_m0
```

## M1: Navigator

**Goal:** prove the learning route changes based on learner state.

**Build:**

- route planning from the concept DAG,
- evidence-bound quiz items,
- prerequisite diagnosis,
- `replan` with `route_version + 1`,
- traceable rationale.

**Gate G1:**

- correct answer advances,
- wrong prerequisite answer inserts a prerequisite,
- `route_version` changes,
- rationale cites quiz result and prereq edge,
- result is recordable in a thin UI or transcript.

## M2: Tutor

**Goal:** prove it teaches and reteaches, not just routes.

**Build:**

- `teach` with cited chunks,
- Socratic `check`,
- misconception detection in `grade` (LLM when `provider=qwen`, deterministic keyword fallback when `none`),
- `reteach` with unused strategy selection,
- `concede` route for exhausted reteach,
- `tutor_turns`,
- parallel pre/post quiz items for demo-core concepts.

**Gate G2:**

- true three-path branching exists: advance, reteach, diagnose/replan,
- reteach strategy changes,
- `concede` prevents infinite loops,
- post-check score exceeds pre-check score in the demo path,
- teaching assertions point to real chunk ids.

## M3: Literature-Induced Scaffolding

**Goal:** prove the project’s main novelty.

**Build:**

- `induce_scaffold` (LLM extraction when `provider=qwen`, offline fixture fallback when `none`; confidence always rule-computed),
- induced prerequisite edge,
- induced misconception,
- `source='induced'`,
- `confidence_basis`,
- frontier flag: consensus, contested, or open,
- UI distinction between curated and induced elements.

**Gate G3:**

- at least one induced edge or misconception is created,
- induced element has cited evidence,
- confidence is rule-computed,
- induced element is used in teaching or routing,
- provenance is visible in demo.

## M4: Polish

**Goal:** improve clarity, resilience, and judging experience after the core is stable.

**Candidate work:**

- ✅ intent/audience modes (researcher vs journalist): implemented — planner target-scoping + frontier-first ordering + depth-aware teach; see `python -m litnav.app demo-intent`,
- decision-trace UI polish,
- jump-step pushback,
- coverage warning,
- hybrid retrieval,
- Chroma/vector retrieval,
- better graph view,
- cross-session memory.

**Gate G4:**

Only add M4 work if M3 is already recordable. M4 should not risk the latest stable submission.

## Beyond M4: Interactive Agent Product UI (productization, not a competition gate)

The current `litnav/ui` panel is **read-only observability** — it renders a session that already ran. The productized end-state is an **interactive agent interface**: the user types a goal, the tutor teaches, asks a quiz, the user actually answers, and the agent adapts live (reteach / replan / induce).

**Status: shipped** at `GET /tutor` (`litnav/ui/interactive.py` + server routes): **type a free-text goal** → the agent plans, teaches (LLM-grounded, typewriter), quizzes, and adapts (reteach / replan / induce) live, via `interrupt_after=["check"]` + resume, with per-session DB/checkpoint files. Two switchable views — **Chat** and a **Glass box** that streams the agent's per-node flow + cited evidence + cost over SSE. Intent modes (researcher/journalist) are selectable in-UI; out-of-scope goals get an honest decline. Sessions are in-memory.

This is **not** a competition gate (the gated core is M0–M3; the recordable demo uses the panel + CLI). It is the "real users use it" form. Architecturally the path is short because the backend already supports human-in-the-loop:

- **Built:** the M1 `SqliteSaver` interrupt/resume; the two-view front-end (`/tutor` + `agent.html`: Chat + Glass box); free-text goal entry (`litnav/goal.py`); per-node SSE streaming (`/tutor/{sid}/events`); LLM-grounded teach; intent modes in-UI; per-session DB/checkpoint (`TutorSession`). (CLI demos still use batch `pending_answers`.)
- **Remaining:** (a) session persistence across server restart (sessions are in-memory) + cleanup of per-session files; (b) wiring the missing-prerequisite reroute into the free-text UI (today it's a CLI/gate path, `demo-reroute`).

So the productized agent UI is in place; what's left is persistence and folding the reroute path into the live UI — not an architecture rewrite.

## Timeline Checkpoints

| Checkpoint | Ideal state | If behind |
|---|---|---|
| late D2 | M0 passes | stop ingestion/UI and secure deterministic SQLite loop |
| late D3 | M1 data package has started | trim to 30 papers / 8 concepts |
| late D5 | M1 passes | freeze M1 as fallback, compress M2 |
| late D7 | M2 passes | freeze M2, reduce M3 to minimal induced fixture + evidence trace |
| late D8 | M3 passes | record M3; if unstable, record M2 and present M3 evidence screenshots |
| D9 | highest stable phase recorded | polish only |
| D10 | deck and submission ready | submit early |

## Stable Snapshot Rule

Tag or save a runnable snapshot whenever a gate passes. Every later milestone is a superset, not a replacement for the last stable submission.
