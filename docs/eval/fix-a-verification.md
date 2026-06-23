# Fix A — Live Verification

Multi-source digest + survey-priority + Wikipedia full-article. 485 offline tests green.

## Results

**Adversarial DISCOVER battery: 12/13 (92%)** — no regression vs the pre-Fix-A ~92% (the one "miss" is
the battery judge over-strict on a correct Adam paper). Survey boost did not hurt on-topic rate.

**Mechanics verified working:**
- `is_review` detection + intent-aware boost: for "introduction to graph neural networks" a review paper
  — *"Graph convolutional networks: a comprehensive review"* — was detected and ordered FIRST as the
  general-concepts backbone.
- Top-3 multi-source digest: the caller now feeds up to 3 sources (backbone first), not 1.
- Extraction nudge: the memory-goal plan is more general ("structured task state tracking" rather than
  the raw "TMT" acronym).

**Honest limitation — outcome is gated by RETRIEVAL:**
For "how do agents remember things across steps", DISCOVER returned **3 narrow primary papers** (TME,
KV-cache, Governed-Memory) and **no survey / no Wikipedia article**, so the plan is still TME-flavored
(though more general in wording). Fix A surfaces/uses a general backbone *when one is retrieved*; for
this niche phrasing none was, because:
1. No prominent survey exists for the exact query, AND
2. **Wikipedia search on the raw conversational goal returns garbage** — "how do agents remember things
   across steps" → *"List of Agents of S.H.I.E.L.D. characters"*; "agent memory" → a film + "AI agent".
   The full-article upgrade (A.3) is correct, but the article never enters `withft` because the search
   uses the **raw goal**, not a normalized topic.

## Next lever (new finding, not in Fix A scope)
**Query normalization for adapter search** — search a cleaned topic ("agent memory in LLMs"), not the
raw conversational goal. The paper adapters tolerate this (gpt-5.4 + relevance gate), but Wikipedia's
keyword search is brittle and needs a normalized query to retrieve the right general article. This is
the highest-leverage follow-up for getting a general backbone on niche/conversational goals.

## Verdict
Fix A is correct, tested, and regression-free, and it measurably improves plan generality **when a
survey/Wikipedia source is retrieved** (GNN case). It does NOT fully solve the niche-goal narrow-plan
problem on its own — that needs query normalization so a general backbone is actually found.

## Follow-up done: Wikipedia best-match reranker
The "next lever" above (Wikipedia query brittleness) is addressed without a new LLM call: the adapter
now fetches a candidate pool and re-ranks by topical match + junk penalty, so the right article
survives to the existing LLM relevance_gate. Live: "agent memory across steps" → [AI agent, Cognitive
model, Reinforcement learning] (was "The 39 Steps (1935 film)"). 487 tests green.
