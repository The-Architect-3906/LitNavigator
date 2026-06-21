# Open-World LitNavigator — a real run, step by step

This is a **concrete walkthrough of one actual live run** — scenario 4 of the 10-scenario suite:
*"Explain the basics of quantum error correction for a beginner"* (English · goal **survey** · learner
variant **lost-then-recover**). Every quote below is from the captured transcript
([`e2e-logs/storyboard-qec.json`](e2e-logs/storyboard-qec.json)); the run mastered **4/4 concepts in 13
turns for ~$0.019**, all live. It shows what each step *says and does*, the **research method / paper**
behind it, and the **skill.md + implementation** that runs it.

![Open-world storyboard](open-world-storyboard.png)

## Step by step (what happened · method/paper · skill & code)

| # | Step — what happened in this run | Research method / paper | Skill.md & implementation |
|--|--|--|--|
| ① | **DISCOVER.** Normalized the goal → search query *"quantum error correction basics"*; intent = `crash-course`; picked the source *"Quantum Error Correction Via Noise Guessing Decoding"* (4 chunks) after dropping off-topic hits. | BM25 (Robertson & Zaragoza) · embedding rerank (SPECTER → `text-embedding-3-small`) · LLM relevance gate + query-normalize (OW-3.1) | **`litnav/discover/SKILL.md`** · `query.py` · `intent.py` · `adapters/{openalex,wikipedia}.py` · `rank.py` · `relevance.py` · `fulltext.py` · `find_sources.py` |
| ② | **DIGEST.** Extracted 8 concepts (`stabilizer_codes`, `QECCs`, `finite_blocklength`, `GRAND`, …), built prerequisite + similarity edges, persisted a cited concept graph to SQLite. | Prerequisite edges via **RefD — Liang et al., EMNLP 2015**, blended with an LLM judge; GraphRAG-style extraction; `gpt-4o` edge verification | **`litnav/digest/SKILL.md`** · `extract.py` · `edges.py` · `refd.py` · `verify.py` · `pipeline.py` |
| ③ | **ORIENT.** Classified goal = `survey` → Bloom ceiling = `comprehension`; planned the route *Stabilizer Codes → QECCs → Finite Blocklength → GRAND*; gave a one-paragraph roadmap. | **Bloom's taxonomy** (Anderson & Krathwohl) · goal modes (mastery/functional/survey) | nodes `goal_elicit.py` · `planner.py` · `orient_tour.py` · ceiling in `state.py` *(graph nodes — no separate SKILL.md)* |
| ④ | **TEACH.** Taught the keypoint: *"Stabilizer codes are a class of quantum error-correcting codes that use the stabilizer-group framework to protect quantum information from noise…"*, grounded in cited evidence. | **Mayer** multimedia principles · worked-example effect (**Sweller**) · goal×expertise×mastery strategy policy | node `teach_kp.py` · `litnav/assess/strategy.py` |
| ⑤ | **ASSESS.** Posed a recall quiz: *"What is the purpose of stabilizer codes in quantum error correction?"* (distractors flaw-gated; difficulty calibrated). | Bloom-leveled QG (**BloomLLM**, Scaria et al.) · **SAQUET** distractor flaw gate · difficulty via weaker-LLM sim + IRT (**SMART**) | node `assess_next.py` · `litnav/assess/quizgen.py` |
| ⑤′ | **"I'm lost" → re-explain.** The learner signalled confusion; the tutor switched to an analogy — *"Think of stabilizer codes like a group of friends solving a puzzle together…"* — **without grading**, then re-posed the question. | Metacognitive scaffolding · strategy switch (analogy → worked-example → contrast → direct) | node `handle_lost.py` |
| ⑥ | **GRADE.** Answer *"to correct errors in quantum information"* → **correct**; feedback *"correctly identifies the purpose"*; mastery 0.30 → 0.48. | **BKT** (Corbett & Anderson 1995) / Rasch-IRT mastery — **never LLM self-judgement** | node `grade_kp.py` · `litnav/state.py` (BKT) |
| ⑥′ | **Climb Bloom.** Correct → raised to `comprehension`, re-quizzed; mastery 0.69 → 0.81 (capped at the survey ceiling, not pushed to `application`). | Bloom ladder + **ceiling** (this run's bug-fix: stop at the ceiling, then check mastery) | `assess_decider` in `grade_kp.py` |
| ⑦ | **ADVANCE.** mastery 0.81 ≥ 0.75 and confidence 0.9 → concept marked **done**; moved to the next concept. | Dual-threshold advance (mastery + confidence ≥ 2 observations) | node `route_decider.py` (`advance_kp_node`) |
| 🔁 | Repeated ④–⑦ for QECCs → Finite Blocklength → GRAND → **all 4 mastered**. | prerequisite-ordered route | `select_next.py` · LangGraph loop |
| ⑧ | **MAKE-ARTIFACT.** Produced Cornell notes **in the learner's language** (English), cited `c1,c2`: *"## QECCs — Cues: role in quantum communication? — Summary: essential for reliable…"* | **Mayer** · testing/retrieval-practice effect (**Roediger & Karpicke 2006**) · output-language localization (A8) | **`litnav/artifact/SKILL.md`** · `selector.py` · `renderers/{notes,slides,mindmap,worked_example}.py` · `make_artifact.py` |
| ✻ | **Orchestration (every step).** The outer agent picks which skill to run per state. | **ReAct** (Yao 2022, arXiv:2210.03629) + **Plan-and-Solve** (Wang 2023) | `litnav/graph/builder.py` (LangGraph `StateGraph` + SqliteSaver) |
| ✻ | **Cost (every call).** One metered router; cheap tier by default, frontier only when needed; BKT/Rasch routing is free; per-session budget cap. | model cascade — **FrugalGPT** · **RouteLLM** (ACL 2025) | `litnav/llm/{router,registry,result_cache}.py` · `storage/cost_repo.py` |

> Skills written as `SKILL.md` today: **find-sources**, **digest-corpus**, **make-artifact**. The
> teach/assess inner loop is implemented as LangGraph nodes (no separate SKILL.md yet); recommend-next
> is OW-6 (pending). Full literature grades: [`2026-06-20-open-world-literature-review.md`](2026-06-20-open-world-literature-review.md).
