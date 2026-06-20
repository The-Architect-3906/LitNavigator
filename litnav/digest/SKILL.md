# digest-corpus

Turn a fixed set of sources into a teachable graph slice: concepts, typed (prerequisite/similarity)
edges with transparent confidence, evidence-bound keypoints, and quiz seeds — written into the concept
graph as `source='digested'`, metered through `litnav/llm/router.py`, and cached per slice.

## Contract
- **In:** `DigestInput{domain_key, sources:[SourceDoc], target_slugs:[]}` + a `candidate` (offline
  replay / live fallback).
- **Out:** `DigestResult{concepts, edges, keypoints, quiz_seeds, unverified_edges, edge_accuracy, cache_hit}`.

## Offline determinism
With `LITNAV_LLM_PROVIDER=none` the pipeline replays the candidate and computes confidence via
`induced_confidence` — deterministic at $0. `python -m litnav.evaluation.verify_digest` is the gate;
`python -m litnav.app digest-demo` runs it on the fixture slice.

## Cost
Extraction + strength labelling use the `cheap` tier; the verify pass uses `frontier` on high-impact
edges only; embeddings use the `embed` tier. Every call writes `cost_ledger`.

## Trust
Prereq edges are a SOFT constraint: below `VERIFY_THRESHOLD` (0.60) or rejected by the verify judge,
an edge is downgraded to `similarity` and flagged in `unverified_edges`. The `edge_accuracy` spot-check
is surfaced (lit-review risk A).
