# digest-corpus

Turn a fixed set of sources into a teachable graph slice: concepts, typed (prerequisite/similarity)
edges with transparent confidence, evidence-bound keypoints, and quiz seeds — written into the concept
graph as `source='digested'`, metered through `litnav/llm/router.py`, and cached per slice.

## Contract
- **In:** `DigestInput{domain_key, sources:[SourceDoc], target_slugs:[]}` + a `candidate` (offline
  replay / live fallback).
- **Out:** `DigestResult{concepts, edges, keypoints, quiz_seeds, unverified_edges, edge_accuracy, cache_hit}`.

## Validation
- **Capability gate (LIVE):** `LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_digest_live`
  — real LLM extracts concepts + proposes edges; asserts edges over extracted slugs, evidence
  resolves, quality floor, real metered cost. THIS proves the skill works.
- **Determinism/schema unit gate (offline):** `python -m litnav.evaluation.verify_digest` — validates
  the confidence formula, downgrade rule, PK ordering, slice_key, cache. NOT capability evidence.
- **Offline smoke:** `python -m litnav.app digest-demo` (provider forced none, deterministic).

## Cost
Extraction + strength labelling use the `cheap` tier; the verify pass uses `frontier` on high-impact
edges only; embeddings use the `embed` tier. Every call writes `cost_ledger`.

## Trust
Prereq edges are a SOFT constraint: below `VERIFY_THRESHOLD` (0.60) or rejected by the verify judge,
an edge is downgraded to `similarity` and flagged in `unverified_edges`. The `edge_accuracy` spot-check
is surfaced (lit-review risk A).
