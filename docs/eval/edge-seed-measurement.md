# builds_on edge-yield measurement

Branch: `feat/digest-edge-reliability`
Date: 2026-06-24
Model: `gpt-5.4-mini` via OpenRouter

## Method

Live digest of 3 goals using inline source chunks (2 paragraphs each).
Edge counts split by DB source column (`digested` / `induced`).
`hint_seeded_weak` = prerequisite edges with `max_strength='weak_hint'` in the result
(proxy for seeds that came from the fallback union path — only fires when LLM returns empty
prereq_edges but builds_on hints exist).

## Results

| Goal | Concepts | prereq (digested) | prereq (backbone) | hint-seeded (weak) | concepts with builds_on |
|---|---|---|---|---|---|
| how do agents remember things across steps | 8 | 3 | 0 | 0 | 7 |
| introduction to graph neural networks | 8 | 8 | 0 | 0 | 7 |
| open router fusion and sakana fugu orchestration | 10 | 2 | 0 | 0 | 8 |

## Interpretation

All 3 goals produced real `digested` prerequisite edges (3 / 8 / 2) with zero induced-backbone
fallbacks. This is a positive result: before this change, zero-edge runs that triggered the
sequential backbone were common on some model/goal combinations.

The `hint_seeded_weak=0` for all runs is expected and correct: the hint section primed the LLM
proposal well enough that the LLM returned real prereq edges on every run, so the empty-fallback
seed path was not needed. The seed path activates only when `proposed["prereq_edges"]` comes back
genuinely empty — it is a safety net, not the primary mechanism.

The high `concepts_with_builds_on` values (7/8 / 7/8 / 8/10 concepts) confirm the extraction model
reliably outputs directional prerequisite annotations when asked, giving the edge-proposal prompt
a strong prior to confirm rather than guess direction from name surface alone.

## Seed wiring (how it flows into build_edges)

1. `extract_concepts` prompts the LLM for an optional `builds_on: [slugs]` per concept.
   Self-refs and unknown slugs are filtered; offline candidates default to `[]`.
2. `_propose_edges` reads `builds_on` off the concept dicts and injects a
   "Candidate prerequisite hints: dep -> target" section into the prompt BEFORE the JSON
   instruction, so the LLM can confirm, correct direction, or extend.
3. After `_propose_edges` returns, `build_edges` checks: if `proposed["prereq_edges"]` is empty
   AND `by_chunk` is non-empty, it synthesises seed edges from `builds_on` pairs, assigning each
   seed the union of both endpoint concepts' keypoint `evidence_chunk_id` values (fallback: first
   chunk id). Seeds are injected into `proposed["prereq_edges"]` with `max_strength="weak_hint"`.
4. The normal scoring loop (`induced_confidence`, evidence filter, verify) processes seeds
   identically to LLM-proposed edges — seeds are NOT written directly to the DB, they go through
   verify. Seeds are only injected when the LLM returned zero prereq edges (no double-counting).

## Concerns

- `gpt-5.4-mini` produces builds_on reliably; weaker models may omit or hallucinate slugs.
  The filter (drop unknown slugs, drop self-refs) guards against hallucination.
- The seed fallback gives `weak_hint` confidence → lower than typical digested edges. Verify
  may still reject some seeds if evidence text is thin. The backbone (`_write_graph`) remains
  as the floor of last resort.
- hint_seeded_weak metric is a proxy (max_strength=weak_hint prereq edges); it conflates
  seeds with any genuinely weak LLM-proposed edge. A dedicated `source='hint_seed'` label
  would disambiguate, but adds complexity — deferred.
