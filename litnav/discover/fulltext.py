"""Fetch full text for the top-k sources. arXiv -> real PDF extract (reuse ingest.corpus_expand);
others -> the abstract as a single chunk."""
from __future__ import annotations
from litnav.discover.contract import Source


def fetch_fulltext(source: Source, *, max_chunks: int = 6) -> list[str]:
    if source.arxiv_id:
        try:  # pragma: no cover - network
            from litnav.ingest.corpus_expand import _download_and_extract
            paper = _download_and_extract(source.arxiv_id)
            if paper and paper.get("chunks"):
                return paper["chunks"][:max_chunks]
        except Exception:
            pass
    return [source.abstract] if source.abstract else []


def attach_fulltext(sources: list[Source], *, top_k: int) -> None:
    """Fill .chunks for the top_k sources (in place)."""
    for s in sources[:top_k]:
        s.chunks = fetch_fulltext(s)
