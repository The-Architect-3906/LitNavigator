"""Extract real text chunks from the agent paper pack into a seed corpus.

Offline, no API, no embeddings — pure PDF text extraction (pypdf) + a curated
paper -> concept mapping. Produces `data/seed/agents_corpus.json`, a complete
fixture (curated concept skeleton + curated misconception/quiz, but with chunks
that are REAL extracted paper text instead of hand-authored representative text).

Regenerate:  python -m litnav.ingest.pdf_extract
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PAPERS_DIR = Path("papers/agent-competition")
OUTPUT = Path("data/seed/agents_corpus.json")
TOPIC = "LLM-based autonomous agents"

# Curated concept skeleton (human-confirmed), shared with the demo fixtures.
CONCEPTS = [
    {"id": 1, "slug": "react", "name": "ReAct (reasoning + acting)", "is_demo_core": 1, "frontier_flag": "consensus"},
    {"id": 2, "slug": "tool_use", "name": "Tool use", "frontier_flag": "consensus"},
    {"id": 3, "slug": "reflection", "name": "Reflection and self-correction", "frontier_flag": "consensus"},
    {"id": 4, "slug": "agent_memory", "name": "Agent memory", "frontier_flag": "consensus"},
    {"id": 5, "slug": "skill_learning", "name": "Skill learning and lifelong agents", "frontier_flag": "consensus"},
    {"id": 6, "slug": "multi_agent", "name": "Multi-agent collaboration", "frontier_flag": "contested"},
    {"id": 7, "slug": "agent_taxonomy", "name": "Agent architecture taxonomy", "frontier_flag": "consensus"},
]
EDGES = [
    (1, 2), (1, 3), (1, 4), (3, 5), (1, 6), (1, 7),
]
SLUG_TO_ID = {c["slug"]: c["id"] for c in CONCEPTS}

# Curated paper -> concept binding (arxiv_id, paper_id, title, year, concept_slug).
PAPERS = [
    ("2210.03629", 1, "ReAct: Synergizing Reasoning and Acting in Language Models", 2022, "react"),
    ("2302.04761", 2, "Toolformer: Language Models Can Teach Themselves to Use Tools", 2023, "tool_use"),
    ("2303.11366", 3, "Reflexion: Language Agents with Verbal Reinforcement Learning", 2023, "reflection"),
    ("2304.03442", 4, "Generative Agents: Interactive Simulacra of Human Behavior", 2023, "agent_memory"),
    ("2305.16291", 5, "Voyager: An Open-Ended Embodied Agent with Large Language Models", 2023, "skill_learning"),
    ("2308.11432", 6, "A Survey on Large Language Model Based Autonomous Agents", 2023, "agent_taxonomy"),
    ("2308.00352", 7, "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework", 2023, "multi_agent"),
    ("2303.17760", 8, "CAMEL: Communicative Agents for Mind Exploration of LLM Society", 2023, "multi_agent"),
]


def _find_pdf(arxiv_id: str) -> Path:
    matches = list(PAPERS_DIR.glob(f"*{arxiv_id}*.pdf"))
    if not matches:
        raise FileNotFoundError(f"no PDF for {arxiv_id} in {PAPERS_DIR}")
    return matches[0]


def _clean(text: str) -> str:
    text = text.replace("­", "")                # soft hyphen
    text = re.sub(r"-\n", "", text)                  # de-hyphenate across line breaks
    text = re.sub(r"arXiv:\S+", " ", text)           # drop arxiv header tokens
    text = re.sub(r"\s+", " ", text)                 # collapse whitespace
    return text.strip()


def extract_text(pdf_path: Path, max_pages: int = 3) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    pages = reader.pages[:max_pages]
    return _clean("\n".join((p.extract_text() or "") for p in pages))


def chunk_text(text: str, target: int = 700, max_chunks: int = 4) -> list[str]:
    chunks: list[str] = []
    i = 0
    while i < len(text) and len(chunks) < max_chunks:
        end = min(i + target, len(text))
        sp = text.find(" ", end)
        if sp != -1 and sp - end < 80:               # extend to a word boundary
            end = sp
        chunk = text[i:end].strip()
        if len(chunk) > 80:
            chunks.append(chunk)
        i = end
    return chunks


def _start_at_abstract(text: str) -> str:
    """Skip the title/author block by starting at the abstract when it's near the top."""
    m = re.search(r"\babstract\b", text, flags=re.IGNORECASE)
    if m and m.start() < 1200:
        return text[m.start():]
    return text[250:] if len(text) > 600 else text  # else trim a typical title block


def extract_paper_chunks(arxiv_id: str, max_pages: int = 3, max_chunks: int = 4) -> list[str]:
    text = _start_at_abstract(extract_text(_find_pdf(arxiv_id), max_pages=max_pages))
    return chunk_text(text, max_chunks=max_chunks)


def build_corpus() -> dict:
    papers_out, chunks_out = [], []
    react_first_chunk = None
    for arxiv_id, pid, title, year, slug in PAPERS:
        papers_out.append({"id": pid, "arxiv_id": arxiv_id, "title": title, "year": year})
        concept_id = SLUG_TO_ID[slug]
        for n, text in enumerate(extract_paper_chunks(arxiv_id), start=1):
            cid = f"c_{arxiv_id}_{n}"
            chunks_out.append({"id": cid, "paper_id": pid, "concept_id": concept_id, "text": text})
            if slug == "react" and react_first_chunk is None:
                react_first_chunk = cid

    # Curated misconception + quiz for the demo-core concept, now cited to a REAL chunk.
    misconceptions = [{
        "id": "react_is_just_cot", "concept_id": SLUG_TO_ID["react"],
        "wrong_model": "ReAct is just chain-of-thought prompting - the model only produces reasoning text.",
        "correct_model": "ReAct interleaves reasoning traces with actions and observations from an external environment.",
        "detect_hint": "chain.?of.?thought|\\bcot\\b|just (reason|think)|only (reason|think)|keyword",
        "reteach_strategy": "analogy", "source": "curated", "confidence": 1.0,
        "evidence_chunk_id": react_first_chunk,
    }]
    quiz_items = [{
        "id": 1, "concept_id": SLUG_TO_ID["react"], "qtype": "explain", "difficulty": 1,
        "question": "In one sentence, what makes ReAct different from plain chain-of-thought prompting?",
        "answer_key": "actions and observations", "evidence_chunk_id": react_first_chunk,
        "source_paper_id": 1, "targets_misconception": "react_is_just_cot",
    }]

    return {
        "topic": TOPIC,
        "targets": ["react", "reflection", "tool_use"],
        "concepts": CONCEPTS,
        "edges": [{"prereq_concept": p, "target_concept": t, "edge_type": "prerequisite",
                   "source": "curated", "confidence": 1.0} for p, t in EDGES],
        "papers": papers_out,
        "chunks": chunks_out,
        "misconceptions": misconceptions,
        "quiz_items": quiz_items,
    }


def main() -> int:
    corpus = build_corpus()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(corpus, indent=2) + "\n", encoding="utf-8")
    per_concept: dict[str, int] = {}
    id_to_slug = {c["id"]: c["slug"] for c in corpus["concepts"]}
    for ch in corpus["chunks"]:
        per_concept[id_to_slug[ch["concept_id"]]] = per_concept.get(id_to_slug[ch["concept_id"]], 0) + 1
    print(f"Wrote {OUTPUT}: {len(corpus['papers'])} papers, {len(corpus['chunks'])} real chunks")
    for slug, n in sorted(per_concept.items()):
        print(f"  {slug}: {n} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
