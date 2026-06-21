# LitNavigator — Backend Roadmap

**Branch:** `feat/open-world-digest` · **Updated:** 2026-06-21

What remains after OW-0..6 land. Items are marked P0 (blocking), P1 (high), P2 (medium),
or **deferred** (recorded for the future, not planned for the current sprint).

---

## OW-7 — Live cold-start, streamed (P0 for demo)

The digest path already works live; OW-7 finishes the **user-facing experience** of a cold start:

- **Streamed progress to the UI:** "finding sources → extracting concepts → building map"
  (currently digest runs in-process and the UI gets the result at the end). Requires the
  frontend SSE streaming to hook into the digest pipeline stages.
- **Demo cache pre-fill:** for the competition demo, one topic's digest cache is pre-filled so
  the shown topic is instant; a genuinely fresh topic shows the real cold path (with streamed
  progress).
- **Multi-source digest for breadth:** the code supports multi-source input; a single-source
  digest still yields 0 surviving prereq edges on some topics (validated A4). OW-7 should
  run the live pipeline with 3+ sources, matching the storyboard scenario.
- **Incremental graph extension:** when the learner strays into a sub-area not in the current
  graph, extend the digest in-session rather than failing silently. Requires inner-loop
  awareness of the graph boundary (OW-4 deferred item).

**Priority:** P0 — this is the demo highlight.

---

## A12 / A13 — Deeper wiring into the auto loop (P1)

**A12 — Prereq-detour (diagnose → replan)** is implemented as graph nodes (`nodes/diagnose.py`,
`nodes/replan.py`) and tested on the legacy path. The keypoint path can trigger it, but the
wiring into the auto outer-loop planner (so the system can autonomously notice a prereq gap and
re-route without human intervention) is not yet end-to-end tested in an automated way.
Action: add a live smoke test that drives a learner into a missing-prereq situation and asserts
the replan fires and resolves.

**A13 — Mid-session goal pivot** (`nodes/goal_pivot.py`) is implemented but not exercised by
the current inner-loop harness. Action: add a `goal_pivot` learner persona to
`inner_loop_scenarios.py` that signals a mid-session intent change and asserts the Bloom ceiling
re-adjusts and the route re-plans.

---

## A14 — Source-specificity / discovery precision (P1)

The A14 fix raised `source_relevance` from 4.0 → 4.78 in the final eval. The remaining gap
(e.g., scenario 3 raft overall=3, borderline source) comes from **goal-specific precision** — the
gate catches obvious off-topic mismatches (a film, a different field), but not "topically adjacent
but wrong" (Raft→PBFT-variant-labeled-as-Raft). Improvements:

- Iterate the query decomposition to include key discriminating terms from the goal (e.g., for
  "Raft consensus algorithm", insist the result is about the Raft log-replication protocol).
- Add a second cheap-LLM specificity check ("is this source specifically about X, or only
  adjacent to X?") for P ≥ 0.5 relevance sources.

---

## Quiz / feedback depth (P1)

**A15 — Quiz variety:** duplicate/repetitive questions within a session reduced by tracking
which question stems were used per concept (persisted in `learner_state`). Further improvement:
generate distractors from error categories (e.g., conceptual swap, off-by-one, negation) rather
than surface paraphrase.

**A16 — Feedback depth:** current explain-why feedback improved from 3.3→3.89. The remaining
gap is **specificity**: the feedback says "that's correct because X" but rarely ties it to the
specific evidence chunk the learner should revisit. Action: ground feedback in `evidence_chunk_id`
and quote the relevant sentence.

---

## Non-English discovery — retry/robustness (P1)

Scenario 10 (GNN · French) hit a transient discovery miss in the final E2E run (recorded as
flaky, not a code defect; it succeeded in prior runs). The issue: multilingual query normalization
produces a good English query, but the OpenAlex/Wikipedia adapters occasionally return 0 full-text
results for niche non-English-named topics, and there is no retry/backoff logic.

Action:
- Add retry with query variation (broaden the query on 0-results) before failing.
- Add a `min_sources` guard that triggers at least one Wikipedia fallback if API results are empty.

---

## Semantic Scholar / YouTube adapters (P2)

Deferred from OW-3:
- **Semantic Scholar adapter** (`adapters/s2.py`): free SPECTER embeddings + TLDRs + 200M paper
  index; better recall than OpenAlex for ML/NLP-specific topics.
- **youtube-transcript-api adapter** (`adapters/youtube.py`): for crash-course / video-first
  learners (intent = `crash-course`); parse `youtube-transcript-api` output into chunks.

These unlock the full source-type stack from the spec (YouTube for crash-course, S2 for systematic).

---

## SPECTER rerank (P2)

Currently: BM25 → `text-embedding-3-small` cosine rerank. Upgrading to SPECTER (free from
Semantic Scholar) would improve scientific paper ranking without extra cost. Deferred pending
Semantic Scholar adapter (above).

---

## Escalation telemetry and pedagogical-error-cost re-tuning (deferred)

The escalation gate (cheap → frontier when low-confidence near mastery threshold) is implemented
but the **escalation rate** is never surfaced in the Glass-box or logged for analysis. Future:
- Log each escalation decision with reason to `cost_ledger` (`escalation_reason` column).
- After 100+ real sessions, re-tune the confidence threshold using the predicted-vs-actual
  `retention_log` data as a proxy for pedagogical-error cost.

---

## Learner_goal slug ↔ ID reconciliation (deferred)

`goal_elicit` persists goals using text slugs; the full-resolution path (slug → canonical concept
ID, then OW-7 live cold-start digest of the concept) is partially done. Full reconciliation
deferred to when OW-7 resolves live slugs→ids.

---

## Multi-session continuity (deferred / post-MVP)

Current `SqliteSaver` checkpoint + `review_queue` give within-session persistence and a FSRS
queue. Cross-session continuity (logging back in, seeing prior sessions, resuming a paused
`review_queue`) requires:
- User identity (currently per-process `session_id` only).
- Frontend session persistence: see [`FRONTEND-ROADMAP.md`](FRONTEND-ROADMAP.md).

---

## Priority summary

| Item | Priority |
|---|---|
| OW-7 live cold-start + streamed progress + demo cache | P0 |
| Multi-source digest for breadth (A4) | P0 |
| A12/A13 auto-loop wiring + harness test | P1 |
| A14 source-specificity second pass | P1 |
| A15/A16 quiz/feedback depth follow-ups | P1 |
| Non-English discovery retry/backoff | P1 |
| Semantic Scholar adapter | P2 |
| YouTube adapter | P2 |
| SPECTER rerank | P2 |
| Escalation telemetry + re-tuning | deferred |
| Learner_goal slug↔ID reconciliation | deferred |
| Multi-session continuity | deferred (post-MVP) |
