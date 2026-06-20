# find-sources (DISCOVER)

Given a learning goal, discover the most suitable real sources and fetch full text for the top-k.

## Contract
- **In:** `DiscoverInput{goal_text, intent?, budget?, k}`.
- **Out:** `DiscoverResult{sources:[Source{source_type,source_id,url,title,authority_score,why,abstract,arxiv_id,chunks}], intent_used}`.

## How
intent classify (cheap LLM seam; offline keyword heuristic) -> query adapters metadata-only
(OpenAlex: papers + citation authority; Wikipedia: encyclopedic background) -> rank
(embedding-cosine relevance vs goal, metered, blended 0.7 + 0.3 authority; offline = authority order)
-> dedup by normalized title -> attach full text for the top-k (arXiv PDF via ingest.pdf_extract;
else abstract). Adapter outages are non-fatal.

## Validation
- **Capability gate (LIVE):** `LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_discover_live`
  — real OpenAlex/Wikipedia + arXiv full text; also feeds the top source into digest to re-measure
  edge quality on RICH evidence (closes A1). THIS proves the skill works.
- **Determinism unit gate (offline):** `python -m litnav.evaluation.verify_discover` — parsing,
  rank math, dedup, intent heuristic. NOT capability evidence.

## Cost
Intent + rerank metered through `litnav.llm.router`; HTTP is bounded (timeout, top-k full text only).

## Recorded deferrals
Semantic Scholar + youtube-transcript adapters; SPECTER rerank (stays `RECORDED_NEEDS` "reranker" —
we use text-embedding-3-small cosine); multi-round iterative discovery for "systematic" intent.
