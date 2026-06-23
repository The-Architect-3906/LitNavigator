# Iterative DISCOVER — Live Measurement

**Date:** 2026-06-24  
**Mode:** live (real LLM)  
**Branch:** feat/iterative-discover  

## Summary

Per-goal: rounds run, refined queries generated, on-topic source count round-1 vs final.

| Goal | Rounds | Refined queries | On-topic R1 | On-topic final |
|------|--------|-----------------|-------------|----------------|
| open router fusion and sakana fugu orchestration | 1 | *(none)* | 3 | 3 |
| I want to understand ReAct | 2 | `language model reasoning planning`, `tool use in language models`, `chain of thought prompting` | 1 | 1 |
| introduction to graph neural networks | 1 | *(none)* | 5 | 5 |

## Detail per goal

### `open router fusion and sakana fugu orchestration`
**Note:** niche/compound — expect refine + round 2  
- Rounds run: 1
- Refined queries: none (round-1 sufficient or offline)
- On-topic sources round 1: 3
- On-topic sources final:   3
- Intent used: cutting-edge
- Final source titles:
  - Sakana Fugu Technical Report
  - SLM-Fusion: A Unified Framework for Model Merging, Routing, and Multi-Model Orchestration
  - Router-R1: Teaching LLMs Multi-Round Routing and Aggregation via Reinforcement Learning

### `I want to understand ReAct`
**Note:** normal → should run 1 round (no refine)  
- Rounds run: 2
- Refined queries (3): ['language model reasoning planning', 'tool use in language models', 'chain of thought prompting']
- On-topic sources round 1: 1
- On-topic sources final:   1
- Intent used: crash-course
- Final source titles:
  - ReAct: Synergizing Reasoning and Acting in Language Models

### `introduction to graph neural networks`
**Note:** normal → should run 1 round (no refine)  
- Rounds run: 1
- Refined queries: none (round-1 sufficient or offline)
- On-topic sources round 1: 5
- On-topic sources final:   5
- Intent used: crash-course
- Final source titles:
  - Introduction to Graph Neural Networks
  - A Gentle Introduction to Graph Neural Networks
  - Graph convolutional networks: a comprehensive review
  - Deeper Insights Into Graph Convolutional Networks for Semi-Supervised Learning
  - Convolutional Neural Networks on Graphs with Fast Localized Spectral Filtering

## Loop control flow

```
Round 1: to_search_query → adapters.search → accumulate candidates dict
  rank_sources(merged_candidates) → relevance_gate(original_goal)
  on_topic = gated set
  if len(on_topic) >= TARGET_SOURCES (2):  stop
  if round >= MAX_ROUNDS (2):               stop
  else: refine_queries(goal, on_topic[:5].titles, intent) → refined_queries
        if refined_queries == []: break  (offline / no ideas)

Round 2 (if reached): for each refined_query: adapters.search → add to candidates
  rank_sources(merged_candidates) → relevance_gate(original_goal)
  on_topic = gated set  → stop (MAX_ROUNDS reached)

After loop: attach_fulltext(final_on_topic, top_k=3) → cache_put → DiscoverResult
```

Key invariants:
- Offline (provider=none): refine_queries returns [] → exactly 1 round
- Dedup by (source_type, source_id) across rounds — merged before re-ranking
- relevance_gate always judges against the ORIGINAL goal (no drift)
- TARGET_SOURCES=2, MAX_ROUNDS=2 (hard cap)

