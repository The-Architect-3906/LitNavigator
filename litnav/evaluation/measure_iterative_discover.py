"""Live measurement: iterative DISCOVER rounds, refined queries, and source counts.

Run with a live provider to get real numbers:
    LITNAV_LLM_PROVIDER=openai .venv/bin/python -m litnav.evaluation.measure_iterative_discover

Saves results to docs/eval/iterative-discover-measurement.md.
"""
from __future__ import annotations
import os
import sqlite3
import textwrap
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def _instrument_find(goal_text: str, k: int = 6) -> dict:
    """Run find() with instrumentation to count rounds, queries, and source counts."""
    from litnav.storage.schema import init_db
    from litnav.discover.contract import DiscoverInput
    from litnav.discover import find_sources, query as query_mod

    conn = sqlite3.connect(":memory:")
    init_db(conn)

    # Instrument refine_queries to capture refined queries
    original_refine = query_mod.refine_queries
    captured_refined: list[list[str]] = []

    def instrumented_refine(goal, prior_titles, intent, **k_kwargs):
        result = original_refine(goal, prior_titles, intent, **k_kwargs)
        captured_refined.append(list(result))
        return result

    # Instrument the search adapters to count round boundaries
    from litnav.discover.adapters import registry as adapter_registry
    from litnav.discover import rank as rank_mod, relevance as relevance_mod

    original_rank = rank_mod.rank_sources
    rank_call_count = [0]
    on_topic_per_round: list[int] = []

    original_gate = relevance_mod.relevance_gate
    gate_results: list[list] = []

    def instrumented_gate(goal, srcs, **k_kwargs):
        result = original_gate(goal, srcs, **k_kwargs)
        gate_results.append(list(result))
        return result

    import unittest.mock as mock
    with mock.patch.object(query_mod, "refine_queries", instrumented_refine), \
         mock.patch.object(relevance_mod, "relevance_gate", instrumented_gate):
        di = DiscoverInput(goal_text=goal_text, k=k)
        result = find_sources.find(di, conn=conn, session_id="measure", budget=200_000)

    rounds_run = len(gate_results)
    refined_queries = captured_refined[0] if captured_refined else []
    on_topic_r1 = len(gate_results[0]) if gate_results else 0
    on_topic_final = len(gate_results[-1]) if gate_results else 0

    return {
        "goal": goal_text,
        "rounds_run": rounds_run,
        "refined_queries": refined_queries,
        "on_topic_round1": on_topic_r1,
        "on_topic_final": on_topic_final,
        "final_sources": [s.title for s in result.sources],
        "intent_used": result.intent_used,
        "cache_hit": result.cache_hit,
    }


def main() -> int:
    provider = os.getenv("LITNAV_LLM_PROVIDER", "none")
    if provider.lower() in ("none", "offline"):
        print("SKIP: set LITNAV_LLM_PROVIDER=openai to run live measurement.")
        print("Writing a placeholder measurement file with offline results...")
        goals_offline = [
            "open router fusion and sakana fugu orchestration",
            "I want to understand ReAct",
            "introduction to graph neural networks",
        ]
        rows = []
        for goal in goals_offline:
            rows.append({
                "goal": goal,
                "rounds_run": 1,
                "refined_queries": [],
                "on_topic_round1": "(offline — passthrough)",
                "on_topic_final": "(offline — passthrough)",
                "final_sources": [],
                "intent_used": "(offline)",
                "cache_hit": False,
                "note": "offline run — provider=none → single round, deterministic",
            })
        _write_md(rows, live=False)
        return 0

    goals = [
        ("open router fusion and sakana fugu orchestration",
         "niche/compound — expect refine + round 2"),
        ("I want to understand ReAct",
         "normal → should run 1 round (no refine)"),
        ("introduction to graph neural networks",
         "normal → should run 1 round (no refine)"),
    ]

    print(f"Running live measurements with provider={provider}")
    print("=" * 60)

    rows = []
    for goal, note in goals:
        print(f"\nGoal: {goal!r}")
        print(f"  ({note})")
        try:
            m = _instrument_find(goal)
            m["note"] = note
            rows.append(m)
            print(f"  rounds_run:      {m['rounds_run']}")
            if m["refined_queries"]:
                print(f"  refined_queries: {m['refined_queries']}")
            else:
                print(f"  refined_queries: (none — single round)")
            print(f"  on_topic_r1:     {m['on_topic_round1']}")
            print(f"  on_topic_final:  {m['on_topic_final']}")
            print(f"  sources:         {m['final_sources']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            rows.append({"goal": goal, "error": str(e), "note": note})

    _write_md(rows, live=True)
    print("\nMeasurement saved to docs/eval/iterative-discover-measurement.md")
    return 0


def _write_md(rows: list[dict], live: bool) -> None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Iterative DISCOVER — Live Measurement",
        "",
        f"**Date:** {date_str}  ",
        f"**Mode:** {'live (real LLM)' if live else 'offline (provider=none — single-round deterministic)'}  ",
        f"**Branch:** feat/iterative-discover  ",
        "",
        "## Summary",
        "",
        "Per-goal: rounds run, refined queries generated, on-topic source count round-1 vs final.",
        "",
        "| Goal | Rounds | Refined queries | On-topic R1 | On-topic final |",
        "|------|--------|-----------------|-------------|----------------|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['goal']} | ERROR | — | — | — |")
            continue
        refined = ", ".join(f"`{q}`" for q in r.get("refined_queries", [])) or "*(none)*"
        lines.append(
            f"| {r['goal']} | {r.get('rounds_run', '?')} "
            f"| {refined} "
            f"| {r.get('on_topic_round1', '?')} "
            f"| {r.get('on_topic_final', '?')} |"
        )
    lines += ["", "## Detail per goal", ""]
    for r in rows:
        lines.append(f"### `{r['goal']}`")
        lines.append(f"**Note:** {r.get('note', '')}  ")
        if "error" in r:
            lines.append(f"**ERROR:** {r['error']}")
            lines.append("")
            continue
        lines.append(f"- Rounds run: {r.get('rounds_run', '?')}")
        if r.get("refined_queries"):
            lines.append(f"- Refined queries ({len(r['refined_queries'])}): {r['refined_queries']}")
        else:
            lines.append("- Refined queries: none (round-1 sufficient or offline)")
        lines.append(f"- On-topic sources round 1: {r.get('on_topic_round1', '?')}")
        lines.append(f"- On-topic sources final:   {r.get('on_topic_final', '?')}")
        lines.append(f"- Intent used: {r.get('intent_used', '?')}")
        if r.get("cache_hit"):
            lines.append("- Cache hit: yes")
        if r.get("final_sources"):
            lines.append("- Final source titles:")
            for t in r["final_sources"]:
                lines.append(f"  - {t}")
        lines.append("")

    lines += [
        "## Loop control flow",
        "",
        "```",
        "Round 1: to_search_query → adapters.search → accumulate candidates dict",
        "  rank_sources(merged_candidates) → relevance_gate(original_goal)",
        "  on_topic = gated set",
        "  if len(on_topic) >= TARGET_SOURCES (2):  stop",
        "  if round >= MAX_ROUNDS (2):               stop",
        "  else: refine_queries(goal, on_topic[:5].titles, intent) → refined_queries",
        "        if refined_queries == []: break  (offline / no ideas)",
        "",
        "Round 2 (if reached): for each refined_query: adapters.search → add to candidates",
        "  rank_sources(merged_candidates) → relevance_gate(original_goal)",
        "  on_topic = gated set  → stop (MAX_ROUNDS reached)",
        "",
        "After loop: attach_fulltext(final_on_topic, top_k=3) → cache_put → DiscoverResult",
        "```",
        "",
        "Key invariants:",
        "- Offline (provider=none): refine_queries returns [] → exactly 1 round",
        "- Dedup by (source_type, source_id) across rounds — merged before re-ranking",
        "- relevance_gate always judges against the ORIGINAL goal (no drift)",
        "- TARGET_SOURCES=2, MAX_ROUNDS=2 (hard cap)",
        "",
    ]

    md_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs", "eval",
        "iterative-discover-measurement.md"
    )
    md_path = os.path.normpath(md_path)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
