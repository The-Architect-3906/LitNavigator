"""Measure the effect of builds_on prereq hints on edge yield.

Runs a live digest of 3 goals and reports per-goal:
  - concept count
  - prereq edge count split by source (digested / induced-backbone / from-hint)

Usage:
  .venv/bin/python scripts/measure_edge_seed.py

Requires LITNAV_LLM_PROVIDER + LITNAV_LLM_API_KEY in .env (real LLM mode).
"""
from __future__ import annotations
import sqlite3
import sys
import os

# Load .env (real LLM mode)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline

GOALS = [
    "how do agents remember things across steps",
    "introduction to graph neural networks",
    "open router fusion and sakana fugu orchestration",
]

# Minimal inline source text to keep the live call cheap. Each goal gets one SourceDoc
# with a brief paragraph that the LLM will decompose into concepts + edges.
SOURCE_TEXTS: dict[str, list[str]] = {
    "how do agents remember things across steps": [
        "AI agents maintain memory across steps using episodic buffers, key-value stores, "
        "and in-context scratchpads. Short-term memory holds recent observations in the context "
        "window. Long-term memory uses retrieval-augmented generation (RAG) to query a vector "
        "database. Episodic memory logs past action-observation pairs timestamped for replay. "
        "Procedural memory encodes reusable skills (e.g. Python code snippets). Memory "
        "consolidation moves important short-term events into long-term storage. Retrieval "
        "policies (recency, relevance, importance) determine what is surfaced at inference time.",
        "Working memory in language models is bounded by context length. Beyond the window, "
        "external memory systems must be queried. A memory router decides which store to hit "
        "based on the query type. Forgetting mechanisms prune stale or low-importance records. "
        "Memory is foundational to planning: agents that cannot recall previous sub-goals loop "
        "or contradict themselves. Compression and summarisation extend effective memory.",
    ],
    "introduction to graph neural networks": [
        "Graph Neural Networks (GNNs) generalize deep learning to irregular graph-structured data. "
        "A graph G=(V,E) has nodes V and edges E. GNNs update each node's representation by "
        "aggregating messages from its neighbors (message passing). Common aggregation functions: "
        "mean, sum, max. Graph Convolutional Networks (GCNs) apply spectral convolution; "
        "GraphSAGE samples neighborhoods for inductive learning. Attention mechanisms (GAT) "
        "weight neighbor contributions. Pooling (global mean/max or hierarchical) produces "
        "graph-level embeddings for classification.",
        "Node classification assigns labels to nodes (e.g. paper → topic). Link prediction "
        "estimates edge existence. Graph classification labels whole graphs (e.g. molecule → property). "
        "Oversmoothing: stacking many layers averages features across the graph, losing structure. "
        "Expressiveness: most GNNs are at most as powerful as the 1-WL test. Skip connections "
        "and normalization layers mitigate oversmoothing. GNNs are used in molecular property "
        "prediction, social network analysis, and knowledge graph completion.",
    ],
    "open router fusion and sakana fugu orchestration": [
        "OpenRouter is a unified API gateway that routes LLM requests to multiple providers "
        "(OpenAI, Anthropic, Mistral, etc.) via a single endpoint. Routing policies include "
        "cost minimisation, latency targeting, and model capability matching. Provider fallback "
        "retries failed requests on an alternate backend. Response fusion merges outputs from "
        "multiple models (mixture-of-experts at inference time). Sakana AI's Fugu is a "
        "multi-agent orchestration framework where a conductor agent decomposes tasks into "
        "sub-goals and dispatches them to specialist worker agents.",
        "Worker agents in Fugu run in parallel; their outputs are merged by a reducer agent. "
        "The conductor maintains a shared memory context. Orchestration overhead is minimised "
        "by caching intermediate results. Fugu supports dynamic agent spawning: workers can "
        "themselves spin up sub-workers. Cost guardrails prevent runaway spend. "
        "Evaluation harnesses run k-of-N trials and assert on aggregate statistics rather than "
        "exact values to handle non-determinism.",
    ],
}

CANDIDATE = {
    "concepts": [],
    "keypoints": [],
    "prereq_edges": [],
    "similarity_edges": [],
    "quiz_seeds": [],
    "misconceptions": [],
    "judge_labels": {},
}


def run_goal(goal: str) -> dict:
    chunks = SOURCE_TEXTS[goal]
    di = DigestInput(
        domain_key=goal,
        sources=[SourceDoc("web", f"measure_{goal[:20]}", goal, None, chunks)],
        target_slugs=[],
    )
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "measure", goal)

    result = pipeline.digest(di, conn=conn, candidate=CANDIDATE, session_id="measure", write=True)

    # Count edges by source in the DB
    rows = conn.execute(
        "SELECT source, count(*) FROM concept_edges WHERE edge_type='prerequisite' GROUP BY source"
    ).fetchall()
    edge_by_source = {src: cnt for src, cnt in rows}

    n_concepts = len(result.concepts)
    n_digested = edge_by_source.get("digested", 0)
    n_induced = edge_by_source.get("induced", 0)

    # "from-hint" = edges that came from the builds_on seed path. These are written as source='digested'
    # because they flow through the normal scoring loop. We detect them by checking if any concept
    # in the result has builds_on entries (proxy: if digested edges exist but only weak_hint ones).
    # More precisely, we check whether any result concept has builds_on set.
    concepts_with_hints = sum(
        1 for c in result.concepts if c.get("builds_on")
    )
    n_hint_edges = sum(
        1 for e in result.edges
        if e.get("max_strength") == "weak_hint" and e.get("edge_type") == "prerequisite"
    )

    return {
        "goal": goal,
        "n_concepts": n_concepts,
        "n_prereq_digested": n_digested,
        "n_prereq_induced_backbone": n_induced,
        "n_hint_seeded_weak": n_hint_edges,
        "concepts_with_builds_on": concepts_with_hints,
        "total_prereq": n_digested + n_induced,
    }


def main():
    provider = os.getenv("LITNAV_LLM_PROVIDER", "none")
    model = os.getenv("LITNAV_LLM_MODEL", "?")
    print(f"Provider: {provider}  Model: {model}\n")

    results = []
    for goal in GOALS:
        print(f"Digesting: {goal!r} ...")
        try:
            r = run_goal(goal)
            results.append(r)
            print(f"  concepts={r['n_concepts']}  "
                  f"digested={r['n_prereq_digested']}  "
                  f"backbone={r['n_prereq_induced_backbone']}  "
                  f"hint-seeded(weak)={r['n_hint_seeded_weak']}  "
                  f"concepts_with_builds_on={r['concepts_with_builds_on']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({"goal": goal, "error": str(exc)})

    print("\n--- Summary ---")
    for r in results:
        if "error" in r:
            print(f"  {r['goal'][:40]!r}: ERROR {r['error']}")
        else:
            has_real = r["n_prereq_digested"] > 0
            label = "REAL EDGES" if has_real else "BACKBONE ONLY"
            print(f"  {r['goal'][:40]!r}: {label}  "
                  f"prereq={r['n_prereq_digested']}+{r['n_prereq_induced_backbone']}(backbone)  "
                  f"hint_seeded={r['n_hint_seeded_weak']}")

    return results


if __name__ == "__main__":
    main()
