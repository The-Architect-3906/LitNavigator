# Design — Iterative DISCOVER (search → observe → refine)

**Date:** 2026-06-24 · **Status:** approved (design discussed + user-approved) → implement
**Branch:** `feat/iterative-discover` (off `main`; backend-only).

## 1. Problem
DISCOVER is single-shot: `goal → normalize → ONE query → adapters → rank → gate → fulltext`. For a
niche/compound goal the literal query matches little, so 0–1 sources survive (live: "open router fusion
and sakana fugu orchestration" → 1 source; OpenAlex 0, Wikipedia 0, S2 429, arXiv 1 on-topic). The home
page also claims "ReAct + Plan-and-Solve · plans · acts · observes · adapts" — but DISCOVER never adapts.

## 2. Approach — a BOUNDED, observe-gated refine loop
Make DISCOVER genuinely agentic: search, **observe yield**, and only when it's thin, **refine the
query** (decompose/broaden) and search again. The common case pays nothing.

```
Round 1: existing path (normalize → adapters → rank → relevance-gate)   [unchanged]
Observe: count on-topic survivors (post-gate, pre-fulltext)
   >= TARGET_SOURCES (K=2)  → stop (most goals)
   <  K and round < MAX_ROUNDS (2) → REFINE:
       cheap LLM: given the goal + round-1 outcome (the few titles found, or "almost nothing"),
       propose 2–3 BROADER / DECOMPOSED English search queries that would find foundational
       sources (e.g. "open router fusion + sakana fugu orchestration" →
       ["LLM model routing and fusion", "multi-agent LLM orchestration", "LLM ensemble routing"]).
   Round 2: search the refined queries → MERGE with round-1 candidates → dedup → re-rank → gate.
Stop: >= K sources, OR MAX_ROUNDS reached.
Then: attach_fulltext(top_k) on the final ranked set (once, as today).
```

### 2.1 Components (`litnav/discover/`)
- **`query.refine_queries(goal, prior_titles, intent, *, conn, session_id, budget) -> list[str]`** (new,
  in `query.py` next to `to_search_query`): cheap-LLM seam, offline passthrough returns `[]` (so offline
  = single-round, deterministic). Returns 2–3 cleaned English sub-queries; de-duped vs the round-1 query.
- **`find_sources.find`** wraps the search+rank+gate block in a bounded loop:
  - `TARGET_SOURCES = 2`, `MAX_ROUNDS = 2` (module constants).
  - Accumulate candidates across rounds in a dict keyed by `(source_type, source_id)` (dedup); re-rank +
    gate the **merged** set each round so cross-round ranking is fair.
  - Refine only when `len(on_topic) < TARGET_SOURCES` AND `round < MAX_ROUNDS` AND provider is live
    (offline `refine_queries` returns `[]` → loop exits after round 1).
  - `attach_fulltext` runs ONCE after the loop (unchanged), on the final ranked set.
- **Cache:** key stays the goal-derived `_query_key` (the loop is internal); a cache hit short-circuits
  the whole loop (unchanged).

### 2.2 Stop / safety (the loop's whole correctness)
- Hard cap `MAX_ROUNDS = 2` (round 1 + at most one refine). No open-ended looping.
- Refine fires only on **low yield** — normal goals (≥2 on-topic in round 1) never pay the extra round.
- Refined queries pass the SAME relevance gate against the ORIGINAL goal → drift is filtered, not taught.
- Budget-aware: refine + round-2 search respect the passed `budget`; cheap tier; cached.
- A refine LLM failure / `[]` → gracefully stop (return round-1 result) — never worse than today.

## 3. Verification
- **Unit (TDD, offline-deterministic):** inject a fake adapter set + fake `refine_fn`/`rank`/`gate`.
  - round 1 yields ≥K → NO refine call (loop stops; common case unchanged).
  - round 1 yields <K → refine called once → round-2 candidates merged + deduped → final ≥ round-1.
  - `MAX_ROUNDS` cap honored (never a 3rd search).
  - offline (`refine_queries` → []) → exactly one round (deterministic; existing tests unaffected).
  - merge dedups by (source_type, source_id); cache hit skips the loop.
- **Offline suite green**; gates G0–G3 pass (DISCOVER stays single-round offline).
- **Live measurement** (report, don't assume): for the sakana goal + 2 normal goals, record rounds run,
  refined queries generated, and on-topic source count round-1 vs final. Expect sakana to gain sources
  via decomposition; normal goals to run exactly 1 round (no regression, no added latency). Save to
  `docs/eval/iterative-discover-measurement.md`.

## 4. Scope guard (YAGNI)
- Backend only — no template changes. (A future UI nicety could stream "refining search…" as a build
  event, but not in scope.)
- 2 rounds max, refine-on-low-yield only. No per-adapter query rewriting, no learned query models.
- Don't touch the relevance gate, ranker, or adapters' contracts — only orchestrate more rounds.

## 5. Risks
- **Latency** on niche goals (the only ones that refine): +1 LLM refine call + 1 extra adapter round
  (~10–30s on an already 30–90s cold start). Accepted — it only happens when round 1 was thin, and a
  streamed "refining…" indicator can be added later.
- **Drift** — mitigated by the unchanged relevance gate judging refined results against the original goal.
- **Non-determinism** rises on the refine path — bounded by MAX_ROUNDS and gated tests stay offline/1-round.
