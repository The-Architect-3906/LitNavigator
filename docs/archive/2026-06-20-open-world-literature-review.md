# Open-World LitNavigator — Literature Review

**Date:** 2026-06-20 · **Branch:** `feat/open-world-digest`
**Method:** ARS `deep-research` **lit-review** mode (bibliography → source-verification →
synthesis). Companion to the [research brief](2026-06-20-open-world-research-brief.md) and
[architecture spec](2026-06-20-open-world-architecture-spec.md).

> **Verification rule (enforced):** ARS IRON RULE — a source that cannot be confirmed to exist is a
> FAIL, not "uncertain." Every entry below was live-confirmed (title + arXiv id / venue) on
> 2026-06-20. **One source (PaperQA2) was excluded** because it was not re-verified live this pass.
> Evidence levels: I = synthesis/meta-analysis, II = RCT/controlled, III = quantitative eval,
> IV = system/applied, V = metric/dataset.

---

## 1. Scope

The decision-critical evidence base for an **open-domain LLM tutoring agent**: source discovery,
concept-graph digest, adaptive teach/assess, multi-format output, agent architecture, and cost
governance. Domain: CS/ML/education (arXiv, ACL/EMNLP/NAACL, AIED/EDM/BEA/LAK, ICLR). Biomedical/
PubMed literature is out of scope.

## 2. Annotated bibliography (verified, graded)

### T1 — Concept & prerequisite-relation extraction / graph construction
- **RefD — Liang et al., "Measuring Prerequisite Relations Among Concepts" (EMNLP 2015).** [V, ✓]
  Reference-Distance metric over Wikipedia links; asymmetric, irreflexive; beat early supervised
  methods. The canonical prerequisite signal.
- **LectureBank — arXiv:1811.12181.** [V, ✓] NLP-education dataset for prerequisite-chain learning
  ("What Should I Learn First").
- **AAAI, "Concept Extraction and Prerequisite Relation Learning"** (ojs.aaai.org/AAAI/article/view/5033). [IV, ✓]
- **Textbook-based prerequisites — arXiv:2011.10337.** [IV, ✓]
- **CLLMRec — arXiv:2511.17041.** [IV, ✓] LLM distills prerequisite relations from course text.
- **KnowLP / GraphRAG-Induced Dual Knowledge Structure Graphs — AAAI 2025, arXiv:2506.22303.** [IV, ✓]
  EDU-GraphRAG builds **prerequisite + similarity** graphs; falls back to similarity when a prereq
  chain blocks the learner.
- **Survey — "Personalized Learning Path Recommendation Based on Knowledge Graphs" (MDPI Electronics 15(1):238).** [I, ✓]
  Names **prerequisite-edge accuracy as the dominant bottleneck**.

### T2 — Learner modeling (knowledge tracing vs LLM self-assessment)
- **"Specialised Knowledge Tracing Models Outperform LLMs" — arXiv:2603.02830.** [III, ✓]
  Specialized KT beats LLMs on accuracy **and** cost.
- **"Confirming Correct, Missing the Rest" — arXiv:2605.16207.** [III, ✓] 7 LLM tutoring agents
  over-validate incorrect reasoning and over-reject valid-but-suboptimal steps; failure is
  model-behavioral, not difficulty-driven.
- **"Twenty-five years of Bayesian Knowledge Tracing: a systematic review" (Springer UMUAI, 2024).** [I, ✓]
  Mastery flags are rarely validated against durable post-tests.

### T3 — Assessment (Bloom-leveled QG, distractors, difficulty, grading)
- **BloomLLM (EC-TEL 2024)** and **Scaria et al. (AIED 2024, arXiv:2408.04394).** [IV, ✓]
  Bloom-leveled QG; LLMs strong at lower Bloom, weak at Analyze/Evaluate/Create.
- **DiVERT — arXiv:2406.19356 (EMNLP 2024).** [III, ✓] MetaMath-Mistral-7B distractor model beats GPT-4o.
- **LookAlike — arXiv:2505.01903 (BEA 2025).** [III, ✓] 51.6% vs DiVERT 45.6% on distractor exact-match.
- **DisGeM — arXiv:2409.18263 (EMNLP-F 2024).** [IV, ✓] Training-free span-masking distractors.
- **D-GEN — arXiv:2504.13439 (ACL-F 2025).** [IV, ✓] Open-source 8B/70B distractor models.
- **SMART — arXiv:2507.05129 (EMNLP 2025).** [IV, ✓] Difficulty via DPO-aligned simulated students + IRT.
- **"Take Out Your Calculators" — arXiv:2601.09953.** [IV, ✓] NAEP difficulty r≈0.82; **weaker models
  simulate difficulty better**; comparison prompting beats absolute.
- **PlausibleQA — arXiv:2502.16358 (SIGIR 2025).** [IV, ✓] Answer-plausibility scores.

### T4 — Adaptive pedagogy
- **Tutor CoPilot — arXiv:2410.03017.** [II, ✓] RCT, 900 tutors / 1,800 K-12 students; **+4 p.p.
  mastery (+9 for lower-rated tutors)**; tutors became "less likely to give away the answer."
- **ITS meta-analysis — arXiv:2511.04997.** [I, ✓] Pooled effect modest (g≈0.27); worked examples
  the strongest moderator.
- **Cepeda et al. (2008), "Spacing Effects in Learning" (Psychological Science).** [II, ✓] Optimal
  first re-check ≈ 10–20% of the target retention interval.
- **Tabibian et al. (2019), MEMORIZE (PNAS).** [II, ✓] Review frequency should scale inverse to
  current recall probability (5.2M Duolingo pairs).
- **Metacognitive vs affective vs neutral feedback (npj Science of Learning, 2025; PMC12000334).** [III, ✓]
  Metacognitive feedback wins on transfer.
- **Worked-example effect & expertise-reversal** (cognitive-load theory; Sweller; Kalyuga et al.). [II,
  classic — textbook, not a single arXiv id].

### T5 — Open-domain source discovery & agentic retrieval
- **STORM — NAACL 2024 ([2024.naacl-long.347](https://aclanthology.org/2024.naacl-long.347/)).** [IV, ✓]
  Multi-perspective question-asking + retrieval for grounded long-form generation.
- **OpenScholar — arXiv:2411.14199.** [III, ✓] Retrieval-augmented LM over 45M papers; cuts citation
  hallucination.
- Academic APIs: **OpenAlex** (~240M works), **Semantic Scholar** (~200M, SPECTER embeddings). [V, ✓]

### T6 — Agent architecture & cost governance
- **ReAct — arXiv:2210.03629; Reflexion — arXiv:2303.11366; MemGPT — arXiv:2310.08560;
  Voyager — arXiv:2305.16291.** [IV, ✓] Reasoning loop / self-critique / long-term memory /
  self-authored skill library.
- **Anthropic Agent Skills (SKILL.md, progressive disclosure).** [IV, ✓]
- **FrugalGPT — arXiv:2305.05176.** [III, ✓] LLM cascade; up to 98% cost reduction at matched quality.
- **RouteLLM — arXiv:2406.18665 (ICLR 2025).** [III, ✓] Learned router; >2× cost reduction.

### T7 — Multi-format output & next-step recommendation
- **Mayer's multimedia-learning principles** + **testing effect**: concept maps for relationships,
  worked examples for procedures, notes for recall, slides for presentation. [II, classic].
- Next-step recommendation: hard prerequisite constraint + soft KT/LLM ranker; deployed
  proficiency-propagation systems (Knewton, Squirrel AI, Duolingo Birdbrain). [IV, ✓ secondary].

**Excluded (IRON RULE):** PaperQA2 (FutureHouse) — cited in the earlier brief but **not re-verified
live** this pass; omitted rather than asserted.

---

## 3. Synthesis (cross-source)

*(Produced by the ARS `synthesis_agent` from the verified corpus above; cleaned of internal protocol
markup. Every claim traces to a bibliography entry.)*

### Unifying principle: **externalized judgment with soft constraints**
The frontier LLM's role should collapse to **orchestration, dialogue, and retrieval-grounded
explanation** — the roles where the agentic and anti-hallucination evidence is strongest (ReAct;
OpenScholar). The *measurement layer* it is demonstrably bad at (correctness, mastery, difficulty)
is externalized to specialized models / IRT-via-simulation, and the *sequencing substrate* treats
prerequisites as soft (KnowLP).

### Themes (with strength)
1. **Small specialized/fine-tuned models beat frontier LLMs on structured sub-tasks — Strong (5
   sources).** Distractors: LookAlike 51.6% > DiVERT 45.6%, DiVERT (7B) > GPT-4o, DisGeM
   training-free, D-GEN open 8B/70B. Learner modeling: specialized KT > LLMs on accuracy *and* cost.
   Frontier scale buys breadth, not precision on constrained objectives.
2. **LLMs are unreliable judges of correctness, mastery, and difficulty — Strong (4 sources).**
   "Confirming Correct" (over-validation of wrong reasoning); difficulty recovered only via
   simulation+IRT, not introspection (SMART, Calculators); BKT review's mastery-validity gap.
   → correctness/mastery/difficulty must be externalized.
3. **Auto-built prerequisite graphs are the central quality risk — Moderate-Strong (3 sources).**
   MDPI survey names edge accuracy the bottleneck; that a SOTA 2025 system (KnowLP) architects a
   similarity *fallback* around prereq fragility is the strongest evidence edges can't be a hard gate.
4. **Adaptive pedagogy works but modestly, mechanism-dependent — Moderate (6 sources).** Tutor
   CoPilot RCT +4/+9 p.p.; but pooled ITS g≈0.27; worked-example effect with expertise-reversal;
   spacing (Cepeda, MEMORIZE); metacognitive feedback wins transfer.
5. **Retrieval & cost governance are mature, transferable infrastructure — Moderate (5+ sources).**
   STORM, OpenScholar; FrugalGPT (≤98%), RouteLLM (>2×); ReAct/Reflexion/MemGPT/Voyager substrate.

### Convergence vs contention (contradictions disclosed)
- *Frontier-is-best* (field default) **vs** *small models win on distractors/KT* → reconcilable:
  task-structure-dependent; holds for narrow schema-constrained sub-tasks only, not open dialogue.
- *Stronger-is-better* **vs** *weaker models simulate difficulty better* (Calculators) → reconcilable:
  a weaker model is a closer proxy for a non-expert student's error distribution. **Bounded** claim
  — simulation fidelity, not general capability.
- *LLMs can assess correctness* **vs** *LLMs over-validate/over-reject* → resolved **against** the LLM
  judge; route to specialized KT.
- *Tutor CoPilot +4/+9 p.p.* **vs** *ITS g≈0.27* → conditional difference (human-mediated RCT vs
  pooled ITS), not a true conflict.
- *Specialized KT accuracy* **vs** *mastery-flag validity gap* → **flagged unresolved**: better KT
  accuracy still doesn't prove the mastery flag predicts durable learning.

### Evidence quality & limitations
The corpus is uneven: **one RCT** (Tutor CoPilot, human-tutor-in-the-loop — does *not* license an
autonomous-tutor claim) and two Level-I syntheses anchor the causal conclusions; most component
results are Level III–IV. Three thinness concerns recur: **(1)** difficulty findings rest on
*simulated* students, not field-administered items; **(2)** the mastery-flag validity gap is inherited
by any mastery signal we consume; **(3)** small-model distractor wins are *benchmark* percentages —
open-domain transfer is untested. Agentic/cost results (ReAct, FrugalGPT, RouteLLM) are
general-purpose, **not** validated in a tutoring loop — importing them is sound engineering but
extrapolation.

### Knowledge gaps (what our system needs but the literature lacks)
1. **No end-to-end evaluation of an autonomous, open-domain LLM tutor** against durable outcomes —
   everything is component-level or human-mediated. → an internal validation study is needed.
2. **Difficulty/mastery never validated against durable post-tests** → triangulate against retention
   probes.
3. **No evidence on prereq-edge accuracy when the graph is built on-the-fly from open-web sources** —
   likely worse than the closed-corpus benchmarks; the hardest case is untested.
4. **Cost routers (FrugalGPT/RouteLLM) tuned on token cost, not pedagogical-error cost** → re-tune
   thresholds so a wrong correctness judgment is priced.
5. **No unified policy** jointly modeling prereq graph + KT state + spacing schedule.
6. **Format-efficacy of LLM-generated artifacts assumed (Mayer/testing-effect), not measured** head-to-head.

### Design implications (cited)
1. **The tutor LLM must not judge correctness or mastery** — route to specialized KT [2603.02830;
   2605.16207].
2. **Prerequisite graph = soft constraint + similarity fallback, never a hard gate** [2506.22303;
   MDPI survey].
3. **Generate distractors/items with small fine-tuned/open models, not the frontier LLM**
   [2406.19356; 2505.01903; 2409.18263; 2504.13439].
4. **Estimate difficulty by student-simulation + IRT with comparison prompting; a deliberately weaker
   simulator can help** [2507.05129; 2601.09953].
5. **Next-step = hard-prereq + soft KT/spacing ranker, explicit spacing params, worked-examples-first
   for novices with fading** [Cepeda 2008; Tabibian 2019; 2511.04997].
6. **Ground all open-domain explanation in retrieval; multi-perspective discovery** [2411.14199;
   STORM].
7. **Cost cascade/router, re-tuned against pedagogical-error cost** [2305.05176; 2406.18665].
8. **Metacognitive-feedback + anti-over-helping defaults** (withhold answers, prompt reflection)
   [2410.03017; npj 2025].

These implications are **already reflected in the architecture spec** — this review verifies their
evidentiary basis and flags where the evidence is thin (esp. on-the-fly prereq accuracy, and
end-to-end outcomes), which the spec's quality gates and confidence-scoring address.

---

## 4. Limitations of this review
- One RCT + two Level-I syntheses carry the causal weight; most component evidence is Level III–IV.
- The cross-paper contradiction scan was **scoped, not exhaustive**.
- Benchmark figures (51.6%/45.6%, r≈0.82) are reported from corpus summaries; primary result tables
  were not re-opened in the synthesis phase.
- Two classic entries (worked-example effect; Mayer principles) are textbook cognitive-science, not
  single citable arXiv ids — labelled as such rather than given a fabricated locator.

## 5. AI-use disclosure
This literature review was produced with AI assistance: the ARS `deep-research` lit-review workflow
(bibliography → source-verification → synthesis) and the `synthesis_agent`. All cited sources were
live-confirmed (title + arXiv id / venue) on 2026-06-20; any source that could not be verified was
excluded rather than asserted. Synthesis claims are traceable to the verified bibliography.
