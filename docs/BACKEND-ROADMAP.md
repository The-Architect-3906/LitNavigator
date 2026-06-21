# Backend — What's Next

*The remaining backend work, in priority order, in plain language.* What already ships:
[BACKEND-COMPLETE](BACKEND-COMPLETE.md). Measured quality that motivates this list:
[E2E-REPORT](E2E-REPORT.md).

Each item is tagged **P0** (blocks the competition demo), **P1** (high value), **P2** (nice to have),
or **deferred** (recorded for later, not this sprint).

---

## 1. Live cold-start, streamed to the screen — *P0*

Today the digest pipeline (find → extract → build map) runs to completion before the UI shows
anything. For a live demo of a *brand-new* topic, the learner should watch it happen.

- **Stream the stages** "finding sources → extracting concepts → building the map → verifying
  links" to the page as they run, instead of one silent wait. (Backend side of the frontend's
  streamed-digest item.)
- **Pre-warm one demo topic** so the headline demo is instant, while a genuinely fresh topic still
  shows the real cold path with live progress.
- **Extend the map mid-session:** if the learner wanders into a sub-area the current map doesn't
  cover, digest it on the fly instead of quietly stopping.

This is the demo centrepiece.

## 2. Multi-source digest for breadth — *P0*

The digest code already accepts several sources, but the live pipeline currently builds from one. A
single source sometimes yields **zero surviving prerequisite links** on a given topic — the
prerequisite signal needs evidence from more than one document to be reliable. Running 3+ sources per
topic (as the storyboard scenario does) is the fix.

## 3. Sharper source discovery — *P1*

Discovery already rejects gross mismatches (a film, a different field); on-topic selection rose to
~4.8/5. The gap left is **adjacent-but-wrong** sources — e.g. a Raft-consensus goal pulling a
*different* consensus protocol that merely mentions Raft.

- Inject the goal's distinguishing terms into the search query (for "Raft consensus", insist on the
  Raft log-replication protocol specifically).
- Add a second cheap-LLM check — "is this source *specifically* about X, or only adjacent to X?" —
  for borderline sources that pass the first relevance gate.

## 4. Robust non-English discovery — *P1*

One scenario (a French goal) hit a *transient* "no full-text source" miss — it succeeded on other
runs, so it's flakiness, not a defect. The English query produced from a non-English goal is good,
but the source APIs occasionally return nothing for niche topics and there's no fallback.

- Retry with a broadened query when the first attempt returns zero results.
- Guarantee a minimum number of sources via a Wikipedia fallback when the paper APIs come up empty.

## 5. Deeper quiz and feedback quality — *P1*

Both improved (quiz ~3.8, feedback ~3.9) but aren't yet uniformly strong.

- **Quiz:** build wrong-answer options from real error *categories* (concept swap, off-by-one,
  negation) rather than surface re-wordings; current variety tracking only avoids repeating stems.
- **Feedback:** tie each explanation to the *specific* evidence sentence the learner should revisit
  (quote it via its `evidence_chunk_id`), instead of a generic "correct because…".

## 6. Finish the autonomous-loop wiring — *P1*

Two adaptive behaviours work but aren't yet exercised end-to-end by the automated harness:

- **Prerequisite detour:** when a learner fails a concept because an *earlier* concept wasn't mastered,
  the tutor detours to teach the missing prerequisite first (`nodes/diagnose.py` → `nodes/replan.py`,
  triggered from the keypoint grader). Add a live smoke test that forces this situation and asserts
  the detour fires and resolves.
- **Mid-session goal change:** `repivot_goal()` in `litnav/nodes/goal_elicit.py` re-elicits the goal
  and re-plans when the learner changes their mind mid-session. Add a learner persona to the
  inner-loop harness that signals a goal change and asserts the depth ceiling and route re-adjust.

## 7. More source types — *P2*

The discovery layer currently queries OpenAlex and Wikipedia
(`litnav/discover/adapters/openalex.py`, `wikipedia.py`). Two more adapters would widen recall:

- **Semantic Scholar** (`adapters/s2.py`): a 200M-paper index with free SPECTER embeddings and
  TLDR summaries — better recall than OpenAlex for ML/NLP topics.
- **YouTube transcripts** (`adapters/youtube.py`): for video-first / crash-course learners.

## 8. SPECTER re-ranking — *P2*

Ranking is currently BM25 → `text-embedding-3-small` cosine. SPECTER embeddings (free via Semantic
Scholar) would improve scientific-paper ranking at no extra cost — but this depends on the Semantic
Scholar adapter above.

## Deferred (recorded, not this sprint)

- **Escalation telemetry & re-tuning:** the grader already escalates from cheap to frontier when
  unsure near the mastery threshold, but the escalation *rate* isn't logged. Record each escalation's
  reason to the cost ledger, then re-tune the confidence threshold once there's real retention data.
- **Goal-to-concept reconciliation:** goals are stored as text slugs; fully resolving a slug to a
  canonical concept (and digesting it live) is only partly wired — finish alongside live cold-start.
- **Across-session continuity:** within-session state persists (checkpoint + review queue), but
  logging back in to resume a paused session needs user identity and a persistent session registry
  (see [FRONTEND-ROADMAP](FRONTEND-ROADMAP.md)).

## Priority summary

| Item | Priority |
|--|--|
| Live cold-start + streamed progress + demo pre-warm | P0 |
| Multi-source digest for breadth | P0 |
| Sharper discovery (adjacent-but-wrong) | P1 |
| Robust non-English discovery (retry + fallback) | P1 |
| Deeper quiz & feedback quality | P1 |
| Finish autonomous-loop wiring (detour + goal-change in harness) | P1 |
| Semantic Scholar adapter | P2 |
| YouTube adapter | P2 |
| SPECTER re-ranking | P2 |
| Escalation telemetry + re-tuning | deferred |
| Goal-to-concept reconciliation | deferred |
| Across-session continuity | deferred |
