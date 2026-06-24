# Refined-Round Judging: Measurement

**Branch**: `feat/refined-round-judging`
**Date**: 2026-06-24
**Change**: Round-2 candidates are now ranked and gated against THAT refined sub-query, not
the original goal. Decomposition now pays off.

---

## The Bug (Before)

The iterative loop broadened the SEARCH in round 2 (decomposed sub-queries like "LLM
orchestration frameworks", "mixture of agents language models" surfaced ~60 candidates) but
still RANKED and GATED every candidate against the ORIGINAL hyper-specific goal text.

Result: genuinely relevant round-2 papers (MoA, RouteLLM, orchestration surveys) scored 1
("same area, different method") and were REJECTED, while a shallow keyword match survived.
The net gain from decomposition was 0–1 weak sources.

## The Fix (After)

For each refined sub-query `rq`:
- Search adapters with `rq`
- Rank results against `rq` (not goal_text)
- Gate that group against `rq` (kept if on-topic for the sub-query, not the niche goal)
- Collect survivors

Final set = round-1 survivors ∪ all refined-query survivors, deduped, then ranked against
`goal_text` for final ordering only (no re-gate — that would undo the fix).

---

## Behavioral Demonstration

### Scenario: Goal too niche for round 1 (0 survivors)

**Goal**: `"openrouter fusion and sakana fugu orchestration"`

**Round-2 sub-queries** (proposed by refine_queries):
- `"LLM orchestration frameworks"`
- `"mixture of agents language models"`

**OLD behavior** (gate round-2 candidates against goal_text):
```
MoA Paper:   score vs goal = 1 → REJECTED  ("same area, different method from openrouter fusion")
RouteLLM:    score vs goal = 1 → REJECTED  ("routing LLMs, not openrouter/fugu specifically")
Orch Survey: score vs goal = 1 → REJECTED  ("adjacent but not the same thing")
Result: 0 survivors from round 2 → 0–1 total weak sources
```

**NEW behavior** (gate each sub-query's candidates against THAT sub-query):
```
Sub-query "LLM orchestration frameworks":
  → RouteLLM:    score vs sub-query = 2 → KEPT
  → Orch Survey: score vs sub-query = 3 → KEPT

Sub-query "mixture of agents language models":
  → MoA Paper:   score vs sub-query = 3 → KEPT

Round-2 survivors: [RouteLLM, orchsurvey, MoA]
Final set (after dedup + rank against goal_text): 3 on-topic sources
```

**End-to-end verification (mocked adapters, confirmed live)**:
```
Final sources (3):
  [web]   'LLM Orchestration Frameworks: A Survey'
  [arxiv] 'RouteLLM: Learning to Route LLMs with Preference Data'
  [arxiv] 'Mixture-of-Agents Enhances Large Language Model Capabilities'

Gate was called with queries:
  - 'openrouter fusion and sakana fugu orchestration'  (round 1 — against original goal)
  - 'LLM orchestration frameworks'                    (round 2, sub-query A)
  - 'mixture of agents language models'               (round 2, sub-query B)
```

---

## Live Measurement: Normal Goals (Single-Round)

These goals reach >= TARGET_SOURCES=2 in round 1 so refine is NOT triggered — unchanged behavior.

### Goal: `"openrouter fusion and sakana fugu orchestration"` (live adapters)

Round 1: 12 candidates → gate passes 2 (already >= TARGET) → refine NOT triggered.

```
Final sources (2):
  [arxiv] 'Sakana Fugu Technical Report'
  [arxiv] 'Challenges and opportunities for AI to help deliver fusion energy'
Search rounds: 1
Gate calls: 1 (with goal_text)
```

### Goal: `"I want to understand ReAct"` (live adapters)

Round 1: 27 candidates → gate passes 3 (>= TARGET) → refine NOT triggered.

```
Final sources (3):
  [arxiv] 'Focused ReAct: Improving ReAct through Reiterate and Early Stop'
  [arxiv] 'Exploring ReAct Prompting for Task-Oriented Dialogue: Insights and Shortcomings'
  [arxiv] 'Reason-Plan-ReAct: A Reasoner-Planner Supervising a ReAct Executor for Complex Enterprise Tasks'
Search rounds: 1
Gate calls: 1 (with goal_text)
```

### Goal: `"introduction to graph neural networks"` (live adapters)

Round 1: 27 candidates → gate passes 4 (>= TARGET) → refine NOT triggered.

```
Final sources (4):
  [web] 'Graph convolutional networks: a comprehensive review'
  [web] 'Introduction to Graph Neural Networks'
  [web] 'A Gentle Introduction to Graph Neural Networks'
  [web] 'Deeper Insights Into Graph Convolutional Networks for Semi-Supervised Learning'
Search rounds: 1
Gate calls: 1 (with goal_text)
```

---

## Loop Control Flow (New)

```
find(di):
  1. Cache check → hit: return immediately.
  2. Round 1:
     raw = _search_adapters(adapters, sq, di.k)
     r1_ranked = rank_sources(goal_text, raw, ...)    # ranked vs goal
     r1_survivors = relevance_gate(goal_text, r1_ranked, ...)  # gated vs goal
     survivors = {(type,id): source for source in r1_survivors}

  3. if len(survivors) < TARGET and MAX_ROUNDS >= 2:
       refined = refine_queries(goal_text, ...)      # [] offline → skips
       for rq in refined:
         rq_raw = _search_adapters(adapters, rq, di.k)
         rq_new = [s for s not already in survivors]
         rq_ranked = rank_sources(rq, rq_new, ...)   # ranked vs SUB-QUERY
         rq_survivors = relevance_gate(rq, rq_ranked, ...)  # gated vs SUB-QUERY
         add rq_survivors to survivors (deduped)

  4. Final ordering:
     ranked = rank_sources(goal_text, list(survivors.values()), ...)  # ordering only
     attach_fulltext(ranked[:3])
     cache and return
```

Key invariants:
- Round 1 gate always uses `goal_text` (strict precision on the original goal).
- Round 2 gate always uses the specific `rq` (not goal_text).
- Final rank uses `goal_text` for ordering only — no re-gate.
- Offline (refine returns []) → single round, identical to before.
- Cache hit → zero adapter calls.
- Round-1 survivors take precedence on dup.

---

## Suite Results

- Full offline suite: **568 passed** (0 failed)
- Acceptance gates G0..G3: **PASS**
- New tests: `tests/test_refined_round_judging.py` — **7 passed**
- Updated test: `test_round2_survivors_included_in_final_rank` (updated from old merged-set test)
