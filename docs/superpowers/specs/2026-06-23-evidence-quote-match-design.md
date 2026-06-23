# Design — Evidence quote-match (fix B1: every keypoint cites c0)

**Date:** 2026-06-23 · **Status:** approved (design discussed + user-approved) → implement
**Branch:** `feat/evidence-quote-match` (off `main`; backend-only, independent of `feat/manuscript-ui`).

## 1. Problem (B1, the most-cited live defect)
Every keypoint/quiz cites the same generic chunk `c0`. Root cause: the extractor LLM emits an
`evidence_chunk_id` that usually doesn't match a real `c{idx}`; `_norm_chunk_id` then **falls back to
`valid_ids[0]` (= c0)** for every unresolvable id, so all keypoints collapse to the first chunk. The
"cited evidence" promise is effectively non-functional on the live path. Increasing chunk supply alone
does NOT fix it — the collapse is in the resolver, not the count.

## 2. Approach — quote-as-authority + id-as-corroboration (no fabricated citations)
The extractor *read* the chunk that produced each keypoint; asking it for an **id** is unreliable
(it guesses), but asking it for a short **verbatim quote** is reliable (it copies). Resolve the chunk
**ourselves, in code, by substring-matching the quote** — exact and verifiable. Keep the id as a
corroborating signal. Never assert a specific chunk we aren't confident about.

### 2.1 Extraction prompt (`litnav/digest/extract.py`)
Add an `evidence_quote` field per keypoint: a SHORT (≤~120-char) **verbatim** span copied from the
evidence that supports the keypoint. Keep the existing `evidence_chunk_id` too. Offline fallback
unchanged (deterministic candidate).

### 2.2 Resolver precedence (`litnav/digest/pipeline.py`) — new `resolve_evidence_chunk(...)`
Returns `(chunk_id | None, confidence_label)`:
1. **quote matches exactly ONE chunk** (normalized substring: lowercase + collapse whitespace) →
   that chunk. If the emitted id ALSO resolves to the same chunk → label `verified`; else `quote-exact`.
2. **quote matches MULTIPLE chunks** → disambiguate with the id (pick the matched chunk whose id ==
   resolved id); else first match. Label `quote-multi`.
3. **quote matches NO chunk, id resolves cleanly to a REAL id** → that id. Label `id-only`.
4. **else embedding fallback**: cosine(keypoint text, chunks) via `chunk_vectors`/`embed_texts`; take
   top **only if ≥ threshold** (`_EVIDENCE_SIM_MIN`, start 0.55). Label `embedding`.
5. **else** → `None`. Label `paper-level` (caller cites the paper, claims no span). NEVER c0-by-default.

### 2.3 `_norm_chunk_id` change (enables corroboration)
Stop returning `valid_ids[0]` on failure — **return `None`** so "real id" is distinguishable from
"gave up". (Today the c0 fallback makes the id always "agree", defeating the cross-check.) Callers that
used the c0 fallback now use the resolver ladder.

### 2.4 Quiz inherits its keypoint's chunk
A quiz tests its keypoint, so `quiz_items.evidence_chunk_id` should **inherit the resolved keypoint
chunk** rather than independently resolving (and re-collapsing). Removes a redundant resolution path
and guarantees the quiz cites the same evidence the lesson did.

### 2.5 Chunk supply (modest)
The resolver can only spread across chunks that exist. Confirm digest uses the multi-source chunks
(Fix A top-3) and lift the per-source chunk cap modestly if needed so distinct relevant chunks exist
to match against. (Tune only if the gold-set accuracy demands it — not the primary lever.)

## 3. Verification
- **Unit (TDD):** `resolve_evidence_chunk` — exact-one, multi+id-tiebreak, id-only, embedding-threshold,
  None/paper-level degrade; `_norm_chunk_id` returns None (not c0) on unresolvable; quiz inherits kp chunk.
- **Gold-set match accuracy:** a small fixture (2 papers, hand-labeled keypoint→correct-chunk); assert
  quote-match resolves the bulk exactly and the embedding fallback + honest-degrade handle the tail;
  report match accuracy + false-positive rate at the threshold. Do NOT ship a matcher we haven't measured.
- **Offline suite stays green** (callers handling the new `None` must not regress).
- **Live spot-check:** a digested concept's keypoints resolve to DISTINCT, relevant chunks (not all c0).

## 4. Scope guard
Backend only — no template changes. The confidence label is returned/persisted for a future UI signal
but wiring it into the manuscript glass box is a separate task on `feat/manuscript-ui`. Keep it minimal.

## 5. Risks
- A wrong-confident citation is worse than an honest vague one → the threshold + honest `paper-level`
  degrade are the guardrails; the gold-set measures the false-positive rate before we trust it.
- `_norm_chunk_id` returning None touches existing callers — must be handled (TDD covers regressions).
