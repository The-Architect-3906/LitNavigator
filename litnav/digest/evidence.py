"""Evidence chunk resolver — quote-as-authority + id-as-corroboration.

Resolves a keypoint's evidence_chunk_id from:
  (1) a verbatim quote substring match (most reliable — LLM copies, not guesses)
  (2) the emitted id as corroboration
  (3) embedding cosine similarity fallback (above threshold only)
  (4) honest paper-level degrade (None) — NEVER the first chunk by default.

See docs/superpowers/specs/2026-06-23-evidence-quote-match-design.md §2.2 for full precedence spec.
"""
from __future__ import annotations

import math
import re

_EVIDENCE_SIM_MIN = 0.55   # minimum cosine similarity for embedding fallback to fire


def _norm_text(text: str) -> str:
    """Lowercase + collapse all whitespace runs to a single space."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


def resolve_evidence_chunk(
    quote: str,
    emitted_id: str | None,
    chunks: dict[str, str],
    *,
    embed_fn=None,
    query_text: str | None = None,
    sim_min: float = _EVIDENCE_SIM_MIN,
) -> tuple[str | None, str]:
    """Resolve a keypoint's evidence to a chunk id, with honest degradation.

    Args:
        quote:      Short verbatim span (≤~120 chars) copied from the source text.
        emitted_id: The chunk id the LLM emitted (may be wrong/hallucinated).
        chunks:     {chunk_id: chunk_text} — all available chunks.
        embed_fn:   Optional callable(list[str]) -> list[list[float]] | None.
                    When None (or when it returns None, as in offline/provider=none
                    mode), the embedding fallback is skipped gracefully.
                    In production, pass embed_texts; in tests, a deterministic fake.
        query_text: Optional fallback query for the embedding step.  When `quote`
                    is empty/whitespace, this text is used as the embedding query
                    instead (e.g. the keypoint name).  Ignored when quote is present.
        sim_min:    Minimum cosine similarity for the embedding fallback to fire.

    Returns:
        (chunk_id | None, label) where label is one of:
            "verified"    — quote matched exactly one chunk AND emitted_id agrees
            "quote-exact" — quote matched exactly one chunk; emitted_id disagreed
            "quote-multi" — quote matched multiple chunks AND id disambiguates
            "id-only"     — no quote match; emitted_id resolves to a real chunk
            "embedding"   — embedding cosine similarity above sim_min
            "paper-level" — nothing resolved; caller cites the paper, not a chunk

    NEVER returns the first chunk as a fallback — returns None instead.
    """
    if not chunks:
        return None, "paper-level"

    # Step 0: resolve emitted_id to a real chunk id (or None)
    id_resolved = emitted_id if emitted_id in chunks else None

    # Normalise the quote for substring search.
    norm_quote = _norm_text(quote) if quote else ""

    # ------------------------------------------------------------------
    # Branch 1 / 2: quote substring match
    # ------------------------------------------------------------------
    if norm_quote:
        matches = [
            cid for cid, text in chunks.items()
            if norm_quote in _norm_text(text)
        ]

        if len(matches) == 1:
            # Branch 1: exactly one chunk contains the quote.
            resolved = matches[0]
            label = "verified" if resolved == id_resolved else "quote-exact"
            return resolved, label

        if len(matches) > 1:
            # Branch 2: multiple chunks contain the quote.
            # Disambiguate ONLY when the emitted id is among the matches.
            # When the id does NOT disambiguate, the quote is ambiguous — fall
            # through to the embedding step rather than blindly returning matches[0].
            if id_resolved and id_resolved in matches:
                return id_resolved, "quote-multi"
            # Ambiguous quote, no id tiebreak → fall through to embedding/paper-level.

    # ------------------------------------------------------------------
    # Branch 3: id corroboration (quote matched nothing, but id is real)
    # ------------------------------------------------------------------
    if id_resolved is not None:
        return id_resolved, "id-only"

    # ------------------------------------------------------------------
    # Branch 4: embedding fallback
    # ------------------------------------------------------------------
    if embed_fn is not None:
        # Use the quote as the embedding query when present; otherwise fall back
        # to query_text (e.g. the keypoint name) so a keypoint with no usable
        # quote can still embed-match on its own semantic content (FIX 2).
        embed_query = (quote.strip() if quote and quote.strip() else None) or (
            query_text.strip() if query_text and query_text.strip() else None
        )
        if embed_query:
            try:
                vecs = embed_fn([embed_query] + list(chunks.values()))
                # embed_fn returns None offline (provider=none) — treat as no signal.
                if vecs is None:
                    pass  # fall through to paper-level
                elif len(vecs) == len(chunks) + 1:
                    query_vec = vecs[0]
                    best_id, best_sim = None, -1.0
                    for cid, chunk_vec in zip(chunks.keys(), vecs[1:]):
                        sim = _cosine(query_vec, chunk_vec)
                        if sim > best_sim:
                            best_sim = sim
                            best_id = cid
                    if best_sim >= sim_min:
                        return best_id, "embedding"
            except Exception:
                pass  # degrade gracefully on embed failure

    # ------------------------------------------------------------------
    # Branch 5: honest paper-level degrade — NEVER default to c0
    # ------------------------------------------------------------------
    return None, "paper-level"
