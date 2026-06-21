# Open-World LitNavigator — user-flow diagram + research basis

This is the **clear, single-altitude** view of what a real learner experiences end-to-end, with each
step's research method / paper / skill named. (The exhaustive node-level graph — every branch, every
internal step — lives in the README + `open-world-architecture.png`; this view is the journey.)

## Why this diagram is laid out the way it is
Diagramming principles applied to fix the "too complex" version:
1. **One altitude (C4 progressive disclosure).** This shows the *user journey*; internal sub-steps and
   every conditional branch are pushed down a level (the detailed graph) instead of crammed in here.
2. **Linear spine + one interactive loop.** The happy path reads top-to-bottom ①→⑥; the only branching
   is the adaptive TEACH⇄ASSESS loop, which is genuinely the heart of the interaction.
3. **Show the human turn.** The `👤 you answer` node makes the real back-and-forth explicit (this is a
   *tutor*, not a pipeline).
4. **Citations go in a table, not in boxes.** Boxes carry a short method tag; full papers are in the
   table below — this is the single biggest readability win.
5. **Cross-cutting concerns are factored out.** The outer agent loop and the cost spine apply to every
   step, so they sit in a separate band instead of tangling edges through the flow.
6. **Colour = skill**, with one legend; numbered steps give an unambiguous reading order.

![Open-world user flow](open-world-flow.png)

## Every step → method / paper / skill

| # | Step (what the user gets) | Skill | Method | Research / paper |
|--|--|--|--|--|
| ① | Find the right real sources for the goal (any language) | **find-sources** | LLM intent classify + multilingual query→English; metadata-first retrieval; keyword prefilter; semantic rerank; LLM relevance gate | OpenAlex & Wikipedia APIs · **BM25** (Robertson & Zaragoza) · **SPECTER** (Cohan et al. 2020) → substituted by `text-embedding-3-small` cosine · relevance gate + query-normalize = OW-3.1 |
| ② | Turn sources into a teachable, prerequisite-ordered concept graph | **digest-corpus** | LLM concept/keypoint extraction (GraphRAG-style); prerequisite edges from a reference-distance signal blended with an LLM judge; frontier verify | **RefD** — Liang et al., *Measuring Prerequisite Relations Among Concepts*, EMNLP 2015 · GraphRAG (Microsoft) · `gpt-4o` evidence-fed edge judge |
| ③ | Set how deep to go (goal elicitation) | **teach** | Goal mode → Bloom ceiling: mastery / functional / survey | **Bloom's taxonomy** (Anderson & Krathwohl, revised) |
| ④a | Teach one keypoint, grounded in cited evidence | **teach** | Multimedia/coherence principles; worked-example effect; goal×expertise×mastery strategy policy | **Mayer**, multimedia learning · **Sweller / Kalyuga**, cognitive load + worked-example & expertise-reversal effects |
| ④b | Quiz at a rising Bloom level | **assess** | Bloom-leveled question generation; overgenerate-and-rank distractors; item-flaw gate | **BloomLLM** (EC-TEL 2024); Scaria et al. (AIED 2024) · **SAQUET** item-writing-flaw gate (AIED 2024) |
| ④c | Calibrate question difficulty | **assess** | Difficulty via a deliberately weaker LLM-simulated student + IRT | **SMART** (EMNLP 2025); *Take Out Your Calculators* (2026, r≈0.82) |
| ④d | Grade the answer → update the learner model | **assess** | Bayesian Knowledge Tracing / Rasch-IRT mastery; rubric grading with uncertainty escalation; **never LLM self-judgement** | **BKT** — Corbett & Anderson 1995 · specialised-KT-beats-LLM (arXiv:2603.02830) · Rasch/1PL (catsim/girth) |
| ④e | Reteach (wrong) / re-explain (lost) / advance (mastered) + schedule review | **teach/assess** | Strategy-switch reteach; metacognitive re-explain; spaced repetition | **FSRS** spaced-repetition scheduler · (LECTOR 2025 semantic-interference — recorded, deferred) |
| ⑤ | A take-away artifact, in the learner's language | **make-artifact** | Format selector → mind-map / Cornell notes / Marp slides / worked-example / combination; retrieval prompt + citations | **Mayer** principles · **testing/retrieval-practice effect** — Roediger & Karpicke 2006 |
| ⑥ | What to learn next | **recommend-next** (OW-6) | Hard-prerequisite filter + soft mastery-gain ranker | — (graph-derived) |
| ✻ | Which skill to run, per state (orchestration) | outer agent loop | ReAct + Plan-and-Solve topology over the skills | **ReAct** — Yao et al. 2022 (arXiv:2210.03629) · **Plan-and-Solve** — Wang et al. 2023 |
| ✻ | Keep every LLM/embed call cheap & bounded | cost spine | Model cascade; cheap pre-filters before paid calls; confidence-gated escalation; per-session budget cap | **FrugalGPT** · **RouteLLM** (ACL 2025) · IRT-Router |

> Full literature grades, evidence levels, and risk flags: [`2026-06-20-open-world-literature-review.md`](2026-06-20-open-world-literature-review.md). Architecture spec: [`2026-06-20-open-world-architecture-spec.md`](2026-06-20-open-world-architecture-spec.md).
