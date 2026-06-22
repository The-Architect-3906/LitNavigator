"""Fetch full text for the top-k sources. arXiv -> real PDF extract (reuse ingest.corpus_expand);
others -> the abstract split into sub-chunks so citations are granular."""
from __future__ import annotations
import re
from litnav.discover.contract import Source


def _chunk_text(text: str, *, target_chars: int = 500, max_chunks: int = 6) -> list[str]:
    """Split text into sentence-packed chunks of ~target_chars each, capped at max_chunks."""
    if len(text) <= target_chars:
        return [text]

    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    sentences = [s for s in sentences if s.strip()]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for sentence in sentences:
        # If adding this sentence would overflow and we already have content, flush
        if current_len + len(sentence) > target_chars and current_parts:
            chunks.append(" ".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(sentence)
        current_len += len(sentence)

    # Flush remaining
    if current_parts:
        chunks.append(" ".join(current_parts))

    # Cap at max_chunks: merge overflow into last chunk so no text is lost
    if len(chunks) > max_chunks:
        overflow = chunks[max_chunks - 1:]
        chunks = chunks[:max_chunks - 1] + [" ".join(overflow)]

    return [c for c in chunks if c.strip()]


def fetch_fulltext(source: Source, *, max_chunks: int = 6) -> list[str]:
    if source.arxiv_id:
        try:  # pragma: no cover - network
            from litnav.ingest.corpus_expand import _download_and_extract
            paper = _download_and_extract(source.arxiv_id)
            if paper and paper.get("chunks"):
                return paper["chunks"][:max_chunks]
        except Exception:
            pass
    if source.source_type == "wikipedia":            # Fix A.3: full article, not the 1-sentence summary
        from litnav.discover.adapters import wikipedia
        art = wikipedia.fetch_article(source.title)
        if art:
            return _chunk_text(art, max_chunks=max_chunks)
    return _chunk_text(source.abstract, max_chunks=max_chunks) if source.abstract else []


def attach_fulltext(sources: list[Source], *, top_k: int) -> None:
    """Fill .chunks for the top_k sources (in place)."""
    for s in sources[:top_k]:
        s.chunks = fetch_fulltext(s)
