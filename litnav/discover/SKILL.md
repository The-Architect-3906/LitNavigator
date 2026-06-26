# find-sources (DISCOVER)

Given a learning goal, discover the most suitable real sources and fetch full text for the top-k.

## Contract
- **In:** `DiscoverInput{goal_text, intent?, budget?, k}`.
- **Out:** `DiscoverResult{sources:[Source{source_type,source_id,url,title,authority_score,why,abstract,arxiv_id,chunks}], intent_used}`.

## How
**query normalize** (cheap LLM: any-language goal -> concise English search query; offline pass-through)
-> intent classify (cheap LLM seam on the ORIGINAL goal; offline keyword heuristic) -> query the
selectable adapter registry metadata-only with the English query (default-on: OpenAlex papers +
citation authority, Semantic Scholar ML-ranked + TLDRs, arXiv preprints, Wikipedia background;
Stack Overflow opt-in) -> rank (embedding-cosine relevance vs the query, metered, blended 0.7 + 0.3 authority;
offline = authority order) -> dedup by normalized title -> **relevance gate** (cheap LLM drops sources
not actually about the topic — a film/different-field page is dropped; never starves: keeps >= min_keep
by rank; offline pass-through) -> attach full text for the top-k (arXiv PDF via ingest.pdf_extract;
else abstract). Adapter outages are non-fatal. The user's original `goal_text` is preserved for intent
and downstream teaching language (OW-3.1, 2026-06-21).

## Validation
- **Capability gate (LIVE):** `LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_discover_live`
  — real OpenAlex/Semantic Scholar/arXiv/Wikipedia + full text; also feeds the top source into digest to re-measure
  edge quality on RICH evidence (closes A1). THIS proves the skill works.
- **Determinism unit gate (offline):** `python -m litnav.evaluation.verify_discover` — parsing,
  rank math, dedup, intent heuristic. NOT capability evidence.

## Cost
Intent + rerank metered through `litnav.llm.router`; HTTP is bounded (timeout, top-k full text only).

## Recorded deferrals
youtube-transcript adapter; SPECTER rerank (stays `RECORDED_NEEDS` "reranker" — we use
text-embedding-3-small cosine). (Semantic Scholar + arXiv adapters and multi-round iterative discovery
are now shipped — see `adapters/registry.py` and `find_sources.py`.)
