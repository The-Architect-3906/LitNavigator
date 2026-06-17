"""Embedding index + semantic retrieval over the paper corpus (M4).

build_index(conn)         — embed every paper_chunk (LITNAV_EMBED_MODEL) and store the
                            vectors in chunk_vectors. No-op offline (provider=none).
semantic_search(conn, q)  — embed the query, rank stored chunk vectors by cosine
                            similarity, return the top-k. Returns [] offline / when the
                            index is empty, so the caller can fall back to concept-tagged
                            retrieval. Cosine is pure-python (no numpy dependency).

Opt-in: retrieve_node only uses this when LITNAV_RETRIEVAL=vector, so the default path and
all offline gates are unchanged.
"""
from __future__ import annotations

import math
import os
import sqlite3

from litnav.llm import client as llm_client
from litnav.storage import repo


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def build_index(conn: sqlite3.Connection) -> int:
    """Embed all paper_chunks and persist their vectors. Returns the number indexed.

    Returns 0 offline (provider=none) or if embeddings are unavailable, leaving the
    deterministic concept-tagged path fully functional."""
    rows = conn.execute("SELECT id, text FROM paper_chunks ORDER BY id").fetchall()
    if not rows:
        return 0
    texts = [r[1] for r in rows]
    vectors = llm_client.embed_texts(texts)
    if vectors is None:           # offline or embedding error -> no index built
        return 0
    model = os.getenv("LITNAV_EMBED_MODEL", "text-embedding-3-small")
    for (chunk_id, _text), vec in zip(rows, vectors):
        repo.save_chunk_vector(conn, chunk_id, vec, model)
    return len(vectors)


def semantic_search(conn: sqlite3.Connection, query: str, top_k: int = 3,
                    concept_id: int | None = None) -> list[dict]:
    """Return the top-k chunks most semantically similar to `query`.

    When `concept_id` is given, ranking is restricted to that concept's chunks — the tutor
    teaches one concept at a time, so evidence must stay in-concept (no cross-concept
    citations). With concept_id=None this ranks the whole corpus (e.g. for exploration).

    Empty list offline, when the (filtered) index is empty, or when query embedding fails —
    so the retrieve node can fall back to concept-tagged evidence transparently."""
    stored = repo.get_chunk_vectors(conn)
    if concept_id is not None:
        stored = [s for s in stored if s["concept_id"] == concept_id]
    if not stored:
        return []
    q = llm_client.embed_texts([query])
    if not q:
        return []
    qvec = q[0]
    ranked = sorted(
        ({"chunk_id": s["chunk_id"], "text": s["text"], "paper_id": s["paper_id"],
          "concept_id": s["concept_id"], "score": round(_cosine(qvec, s["vector"]), 4)}
         for s in stored),
        key=lambda d: d["score"], reverse=True,
    )
    return ranked[:top_k]


def main() -> int:  # pragma: no cover - manual index-build helper
    """Build the embedding index for a seeded corpus DB.

        python -m litnav.retrieval.vector --fixture data/seed/agents_corpus.json
    """
    import argparse
    from pathlib import Path

    from litnav.config import DEMO_DB_PATH, load_dotenv
    from litnav.storage.schema import init_db, reset_db
    from litnav.storage.seed import seed_demo_data

    load_dotenv()
    parser = argparse.ArgumentParser(prog="litnav.retrieval.vector")
    parser.add_argument("--fixture", default="data/seed/agents_corpus.json")
    parser.add_argument("--db", default=DEMO_DB_PATH)
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    reset_db(conn)
    init_db(conn)
    seed_demo_data(conn, args.fixture)
    n = build_index(conn)
    if n == 0:
        print("No index built (provider=none or embeddings unavailable). "
              "Set LITNAV_LLM_PROVIDER=openai in .env to build a real index.")
    else:
        print(f"Indexed {n} chunks into chunk_vectors ({args.db}).")
        for hit in semantic_search(conn, "how do agents reason and act", top_k=3):
            print(f"  score={hit['score']}  chunk={hit['chunk_id']}  "
                  f"concept={hit['concept_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
