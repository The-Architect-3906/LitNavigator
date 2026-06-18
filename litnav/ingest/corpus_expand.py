"""Evidence-only corpus expansion: add more agent papers as retrieval/teaching evidence
without authoring new concepts or quizzes.

build_expanded_fixture() embeds each new chunk, tags it to the nearest existing concept (by
concept-name embedding), and writes agents_m3.json's spine + the appended papers/chunks to a
new fixture. Tutor sessions seed from that fixture, so the broader corpus reaches the live
tutor. Offline (provider=none) embed_texts returns None -> raises a clear error (run with a
provider set); the gates never call this.

CLI:  python -m litnav.ingest.corpus_expand    # downloads the curated arXiv list -> fixture
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from litnav.llm import client as llm_client

# Curated starting list of well-known LLM-agent papers (arXiv ids). VERIFY each id resolves
# and DEDUPE against ids already in the base fixture's papers before downloading; adjust.
ARXIV_IDS = [
    "2302.04761",  # Toolformer
    "2303.17580",  # HuggingGPT
    "2307.16789",  # ToolLLM
    "2308.08155",  # AutoGen
    "2308.00352",  # MetaGPT
    "2303.17760",  # CAMEL
    "2305.10601",  # Tree of Thoughts
    "2308.09687",  # Graph of Thoughts
    "2303.17651",  # Self-Refine
    "2305.18323",  # ReWOO
    "2305.04091",  # Plan-and-Solve
    "2307.07924",  # ChatDev
    "2308.03688",  # AgentBench
    "2305.15334",  # Gorilla
    "2306.06070",  # Mind2Web
    "2307.13854",  # WebArena
    "2309.07864",  # Rise and Potential of LLM-Based Agents (survey)
    "2305.14325",  # Multi-agent debate (society of minds)
    "2302.01560",  # DEPS (describe-explain-plan-select)
    "2305.17390",  # SwiftSage
]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def _nearest_concept(vec: list[float], centroids: dict[int, list[float]]) -> int:
    return max(centroids, key=lambda cid: _cosine(vec, centroids[cid]))


def build_expanded_fixture(base_path: str, papers: list[dict], out_path: str) -> int:
    """Append evidence-only papers to the base fixture, tagging each chunk to its nearest
    concept. Returns the number of chunks appended. Raises if embeddings are unavailable."""
    base = json.loads(Path(base_path).read_text(encoding="utf-8"))
    concepts = base["concepts"]
    concept_vecs = llm_client.embed_texts([c["name"] for c in concepts])
    if not concept_vecs:
        raise RuntimeError("Embeddings unavailable (set LITNAV_LLM_PROVIDER=openai).")
    centroids = {c["id"]: v for c, v in zip(concepts, concept_vecs)}

    base.setdefault("papers", [])
    base.setdefault("chunks", [])
    next_pid = max((p["id"] for p in base["papers"]), default=0) + 1
    added = 0
    for paper in papers:
        chunk_vecs = llm_client.embed_texts(paper["chunks"])
        if not chunk_vecs:
            continue
        base["papers"].append({"id": next_pid, "arxiv_id": paper["arxiv_id"],
                               "title": paper.get("title", paper["arxiv_id"])})
        for i, (text, vec) in enumerate(zip(paper["chunks"], chunk_vecs)):
            base["chunks"].append({
                "id": f"cx_{paper['arxiv_id']}_{i}", "paper_id": next_pid,
                "concept_id": _nearest_concept(vec, centroids),
                "section": "evidence", "chunk_index": i, "text": text,
            })
            added += 1
        next_pid += 1

    Path(out_path).write_text(json.dumps(base, ensure_ascii=True, indent=2), encoding="utf-8")
    return added


def _download_and_extract(arxiv_id: str) -> dict | None:  # pragma: no cover - network
    import urllib.request
    from litnav.ingest.pdf_extract import extract_text, chunk_text, _start_at_abstract  # reuse the extractor
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        import io
        import pypdf
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = reader.pages[:3]
        import re
        raw = re.sub(r"\s+", " ", "\n".join((p.extract_text() or "") for p in pages)).strip()
        text = _start_at_abstract(raw)
        chunks = chunk_text(text, max_chunks=6)
        return {"arxiv_id": arxiv_id, "title": arxiv_id, "chunks": chunks[:6]}
    except Exception as e:
        print(f"skip {arxiv_id}: {e}")
        return None


def main() -> int:  # pragma: no cover - manual
    from litnav.config import load_dotenv
    load_dotenv()
    base = json.loads(Path("data/seed/agents_m3.json").read_text(encoding="utf-8"))
    existing = {p.get("arxiv_id") for p in base.get("papers", [])}
    papers = []
    for aid in ARXIV_IDS:
        if aid in existing:
            continue
        p = _download_and_extract(aid)
        if p and p["chunks"]:
            papers.append(p)
            print(f"fetched {aid} ({len(p['chunks'])} chunks)")
    n = build_expanded_fixture("data/seed/agents_m3.json", papers,
                               "data/seed/agents_expanded.json")
    print(f"wrote data/seed/agents_expanded.json (+{n} evidence chunks, "
          f"{len(papers)} papers). If few succeeded, expansion is de-scopable.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
