"""G-discover-adversarial (LIVE, DRAFT): stress the DISCOVER stage with inputs that are easy to
mis-resolve, and measure how often it acquires an ON-TOPIC source.

Motivation: a live session for goal "I want to understand ReAct" returned advertising-psychology
papers ("Psychological Reactance") — the short term collided with "react/reactance" and the relevance
gate passed a high-authority but off-topic source, so the whole course was built on the wrong paper.
The 10 e2e scenarios never test ambiguous/short/typo/nonsense goals, so nothing guards this.

Oracle: an LLM "on-topic judge" — given the goal and the source DISCOVER chose, does the source match
what the learner most likely meant (canonical technical sense)? This is exactly the topic-match guard
DISCOVER itself lacks today, used here as the test oracle.

Runs LIVE only (real OpenAlex/Wikipedia + LLM). SKIPs unless a provider is configured, like the other
live gates. Reports a per-category on-topic rate + every wrong-sense match (evidence for the fix), and
fails only if the overall rate falls below MIN_ON_TOPIC (default report-only via env).
"""
from __future__ import annotations

import os
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.discover.contract import DiscoverInput
from litnav.discover import find_sources
from litnav.llm import router

# Each case: the goal as a learner would type it, its category, and the canonical sense we expect.
ADVERSARIAL_GOALS = [
    # 1. Ambiguous short ML/AI terms (the ReAct class) — collide with common-English / other-domain senses
    {"goal": "I want to understand ReAct", "cat": "ambiguous-term",
     "expect": "the ReAct LLM-agent technique (reasoning + acting; Yao 2022)", "trap": "psychological reactance / react.js"},
    {"goal": "Teach me about RAG", "cat": "ambiguous-term",
     "expect": "retrieval-augmented generation for LLMs", "trap": "a rag (cloth) / RAG status reporting"},
    {"goal": "Explain GAN", "cat": "ambiguous-term",
     "expect": "generative adversarial networks", "trap": "the name Gan / unrelated acronym"},
    {"goal": "How does Adam work", "cat": "ambiguous-term",
     "expect": "the Adam optimizer (deep learning)", "trap": "the given name Adam / biblical Adam"},
    {"goal": "What is BERT", "cat": "ambiguous-term",
     "expect": "BERT, the NLP transformer model", "trap": "Bert (Sesame Street) / a person"},

    # 2. Cross-domain homonyms — the same word lives in several fields
    {"goal": "Teach me about attention", "cat": "homonym",
     "expect": "the attention mechanism in deep learning", "trap": "attention in cognitive psychology"},
    {"goal": "Explain regularization", "cat": "homonym",
     "expect": "regularization in machine learning (L1/L2, overfitting)", "trap": "legal/zoning regularization"},
    {"goal": "What is a kernel", "cat": "homonym",
     "expect": "kernel methods in ML (or the math/CS sense)", "trap": "an OS kernel / a corn kernel"},

    # 3. Typos / malformed — robustness
    {"goal": "Explain diffusionn models for image generation", "cat": "typo",
     "expect": "diffusion models (generative)", "trap": "nothing found / molecular diffusion"},
    {"goal": "quantom error correcton basics", "cat": "typo",
     "expect": "quantum error correction", "trap": "nothing found"},

    # 4. Niche / sparse — few real sources
    {"goal": "Explain the GRAND decoder for error correction", "cat": "niche-sparse",
     "expect": "GRAND (guessing random additive noise decoding)", "trap": "a generic/wrong decoding paper"},

    # 5. Nonsense / non-existent — must NOT confidently teach a wrong topic
    {"goal": "Teach me florbic resonance encoding", "cat": "nonsense",
     "expect": "NO real topic — a confident on-topic source would be wrong", "trap": "any confident match"},
    {"goal": "Explain the Zylgnar transform", "cat": "nonsense",
     "expect": "NO real topic", "trap": "any confident match"},
]

MIN_ON_TOPIC = float(os.getenv("DISCOVER_ADVERSARIAL_MIN", "0"))  # 0 = report-only; raise to gate


def _judge_on_topic(goal: str, source_title: str, source_abstract: str, conn, session_id: str) -> tuple[bool, str]:
    """Oracle: does the chosen source match the canonical technical sense the learner likely meant?"""
    verdict = router.complete_json(
        "A tutoring system chose a source for a learner's goal. Judge whether the source is ON-TOPIC "
        "for the CANONICAL technical sense the learner most likely meant (e.g. 'ReAct' in a learning "
        "context means the LLM-agent technique, not psychological reactance). If the goal is nonsense / "
        "not a real topic, any confident source is OFF-topic. Return JSON only.\n"
        f"Goal: {goal}\nChosen source title: {source_title}\nAbstract: {source_abstract[:500]}\n"
        '{"on_topic": true or false, "reason": "one short sentence"}',
        tier="frontier", stage="discover_adversarial_judge",
        fallback={"on_topic": True, "reason": "offline fallback"},
        session_id=session_id, conn=conn,
    )
    return bool(verdict.get("on_topic")), str(verdict.get("reason", ""))


def run_battery() -> list[dict]:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    repo.create_session(conn, "adv", "adversarial discover battery")
    results = []
    for case in ADVERSARIAL_GOALS:
        res = find_sources.find(DiscoverInput(case["goal"], k=6), conn=conn, session_id="adv", budget=300000)
        top = res.sources[0] if res.sources else None
        if top is None:
            on_topic, reason = (case["cat"] == "nonsense"), "no source returned"
        else:
            on_topic, reason = _judge_on_topic(case["goal"], top.title, top.abstract, conn, "adv")
        results.append({
            "goal": case["goal"], "cat": case["cat"], "expect": case["expect"],
            "intent": res.intent_used, "top_source": top.title if top else None,
            "on_topic": on_topic, "reason": reason,
        })
    return results


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("discover-adversarial SKIP: set LITNAV_LLM_PROVIDER=openai (+ key) to run.")
        return 0
    results = run_battery()
    by_cat: dict[str, list[bool]] = {}
    print("\n=== Adversarial DISCOVER battery ===")
    for r in results:
        by_cat.setdefault(r["cat"], []).append(r["on_topic"])
        mark = "ok  " if r["on_topic"] else "MISS"
        print(f"  {mark} | {r['cat']:<14} | {r['goal'][:38]:38} | intent={r['intent']:<12} | {r['top_source']}")
        if not r["on_topic"]:
            print(f"        ↳ expected: {r['expect']}  | judge: {r['reason']}")
    n = len(results)
    on = sum(1 for r in results if r["on_topic"])
    print(f"\n  on-topic: {on}/{n} ({on / n:.0%})")
    for cat, vals in sorted(by_cat.items()):
        print(f"    {cat:<14}: {sum(vals)}/{len(vals)}")
    rate = on / n
    if rate < MIN_ON_TOPIC:
        print(f"\nFAIL: on-topic rate {rate:.0%} < MIN_ON_TOPIC {MIN_ON_TOPIC:.0%}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
