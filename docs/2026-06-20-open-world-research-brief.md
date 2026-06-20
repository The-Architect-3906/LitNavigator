# Open-World LitNavigator — Research Brief

**Date:** 2026-06-20 · **Branch:** `feat/open-world-digest`

Synthesis of 5 parallel research threads (source-discovery, digest→concept-graph, adaptive
pedagogy, agent-architecture+cost, multi-format+assessment+next-step) plus their nested
sub-searches. Live search hit a transient outage mid-run but all threads ultimately returned
adversarially-verified, cited briefs. Specific `26xx` arXiv IDs are 2026 papers (plausible given
today's date); confirm before formal citation. This brief feeds the architecture spec.

---

## 0. The one-line synthesis

Build an **open-domain tutor** as a **LangGraph spine** (deterministic teach/assess inner loop)
wrapped by an **agent-with-tools outer loop** that invokes **stage skills** (find-sources, digest,
make-notes/map/slides, recommend-next). The **concept graph stays the spine**; a **BKT/Rasch
learner model — not LLM self-assessment — is the ground truth**; **cost is governed by a three-tier
model cascade + precompute + caching** from day one.

---

## 1. DISCOVER — find the most suitable, complete sources

- **Free backbone APIs:** OpenAlex (~240M works, citation graph), Semantic Scholar (~200M, free
  SPECTER embeddings + TLDRs), arXiv (throttled 1 req/3s), CORE (OA full-text), Crossref,
  Papers With Code, Wikipedia REST, `youtube-transcript-api`. **Never scrape Google Scholar**
  (ToS / CAPTCHA / legal).
- **Intent-first routing (the key move):** classify `{crash-course, systematic, applied,
  reference, cutting-edge}` *before* any API call → source-type stack (crash→Wikipedia+YouTube;
  systematic→papers by citation; applied→Papers With Code+docs; cutting-edge→recent arXiv).
- **Agentic retrieval:** STORM (Stanford, NAACL 2024), OpenScholar (UW 2024, cuts citation
  hallucination 78–90%), PaperQA2 (FutureHouse, Nature 2025; `pip install paper-qa`). Pattern:
  decompose goal → search → read → find gaps → re-query.
- **Cost:** BM25 pre-filter → embed top-50 (RRF hybrid); two-tier (metadata first, full-text only
  top-k); semantic query cache (~31% hit); reuse Semantic Scholar's free SPECTER embeddings.

## 2. DIGEST — sources → concept graph + keypoints + evidence (the core novelty)

- **Prerequisite-relation extraction** is the distinctive, hard part (wiki/KG tools don't produce
  it). Classic signal: **RefD (Reference Distance)** over Wikipedia; "concept prerequisite
  learning" is an established sub-field. LLM distillation: **CLLMRec** (LLM distills prereq
  relations from course text → cognitive-aligned graph, arXiv:2511.17041).
- **Graph construction at scale:** Microsoft **GraphRAG** (entity+typed-relation extraction →
  community detection → hierarchical summary) and **RAPTOR** (recursive summary tree).
  **EDU-GraphRAG / KnowLP** auto-generates prereq + similarity graphs from raw educational data
  (AAAI 2025, arXiv:2506.22303).
- **Inductive concept handling:** **SINKT** (CIKM 2024, arXiv:2407.01245) tracks knowledge on
  *unseen* concepts via LLM semantic embeddings — solves cold-start for arbitrary concepts.
- **Survey + the key risk:** *Personalized Learning Path Recommendation Based on Knowledge
  Graphs: A Survey* (MDPI Electronics 15(1):238) — **prerequisite-edge accuracy is the dominant
  bottleneck** in deployed systems. So: cheap-model extract → **expensive-model verify only
  high-impact edges**; confidence scores; precompute + human-check "warm" domains, live-digest
  only cold ones.

## 3. TEACH — adaptive, multi-format

- **Open with 1 goal-elicitation turn** → **Mastery** (full Bloom sweep, strict thresholds) /
  **Functional** (Bloom 1–3, applied, faster) / **Survey** (breadth-first, no gates).
- **Learner model = BKT/AKT backbone, the LLM reads from it.** Specialized KT beats LLMs on
  accuracy *and* cost ("Faster, Cheaper, More Accurate", 2026). **Do not let the LLM self-assess
  student knowledge — it over-validates wrong reasoning** ("Confirming Correct, Missing the Rest",
  2025). Inductive option: **LLMKT / NTKT** (track KCs from free-form dialogue, arXiv:2409.16490 /
  2511.02599) for open-domain state.
- **Strategy policy** (cheap classifier, not a 2nd LLM): novice→worked-example+direct;
  intermediate→faded examples+Socratic; expert→problem-first (**expertise-reversal effect**).
- **Anti-over-helping is the strongest practical finding:** forbid answer-reveal, require a
  guiding question/hint first. Evidence: **Tutor CoPilot** RCT (Stanford 2024, +4/+9 p.p.
  mastery); **Improving Socratic QG** (DPO, BEA 2024). **Khanmigo**'s 60% drop-off + math
  hallucinations is the cautionary tale.
- **Spacing:** FSRS review queue; **LECTOR** (2025) adds semantic-interference checks. Drain
  overdue reviews at session start.

## 4. ASSESS — Bloom-layered, adaptive, verified

- **Bloom-leveled QG:** **BloomLLM** (EC-TEL 2024), Scaria et al. (AIED/BEA 2024); LLMs are strong
  at Remember/Understand/Apply, weak at Analyze/Evaluate/Create without scaffolding. Controllable
  QG: "Planning First, Question Second" (ACL Findings 2024); **T-CQG** (topic-controlled, T5-small,
  LAK 2025).
- **Distractors (a whole sub-field):** LLMs are weak here — **overgenerate-and-rank** (BEA 2024),
  **LookAlike** (DPO, BEA 2025), **DisGeM** (span-masking, EMNLP 2024 Findings). Evaluate with the
  learned **DISTO** metric (not BLEU). Human-in-loop matters: **HEDGE** found 70% of LLM stems
  valid but only 37% of distractors.
- **Difficulty calibration:** **LLM student-simulation + IRT** is the dominant paradigm — **SMART**
  (DPO-aligned simulated students + IRT, EMNLP 2025), "Take Out Your Calculators" (2026, r≈0.82).
  **Comparison/relative prompting beats absolute** difficulty scoring. Controllable-difficulty QG
  via IRT: Tomikawa & Uto (AIED 2024 → IEEE Access 2026, DPO).
- **Adaptive item selection (CAT):** use **Rasch/1PL** (smallest calibration need), **EAP**
  estimator, **Maximum Fisher Information** selection, **BAMA** personalized mastery-confidence
  stopping. Libraries: **catsim** (Python CAT), **jsCAT** (browser, Stanford), **girth**
  (calibration with MLE/MAP/EAP), **EduCAT**. Cold-start: **AutoIRT** / expert ratings / **BERT-IRT**.
- **Grading:** rubric-conditioned; **GradeOpt** reflector-refiner loop (EDM 2025); RAG-augmented
  grading (EDM 2025). **Quantify uncertainty and escalate low-confidence to human/skip** (the
  "Trust Curve"). **0–5 scale maximizes human-LLM alignment**; binary is robust. Item-quality gate:
  **SAQUET** flags item-writing flaws at 94% (AIED 2024).

## 5. OUTPUT (multi-format) + NEXT-STEP

- **"Artifacts as files":** one grounded knowledge structure → multiple renders by goal.
  - **Slides:** `python-pptx` is the universal renderer; **Marp** is the most LLM-friendly target
    (plain Markdown → PDF/PPTX/HTML, but PPTX text is image-rasterized); **Pandoc** gives
    *editable* `.pptx` via `--reference-doc`. Reference systems: **PPTAgent** (edit-based,
    EMNLP 2025, 4.7k★), **SlideDeck AI** (clean LLM→JSON-schema→python-pptx). Best-practice
    pipeline: multi-stage decomposition + strict JSON schema (`additionalProperties:false`) +
    2-shot examples + a thin DSL over python-pptx (AUTOPRESENT's `SLIDESLIB` cut code 170→13
    lines, +34 pts accuracy).
  - **Mind-map / concept-map:** **Mermaid** or **markmap** — *we already have `concept_graph()` +
    `graph_svg`* to feed it.
  - **Notes:** Markdown study guide from the same structure.
- **Next-step recommender:** **hard prerequisite constraint + soft ranker**. Research: **TutorLLM**
  (KT+RAG, curriculum-free, arXiv:2502.15709), **GenMentor** (goal→skill→path, multi-agent,
  WWW 2025), **SKarREC** (LLM+graph concept rec, arXiv:2405.12442), set-to-sequence ranking
  (AAAI 2023). Deployed patterns: **Knewton** (Bayesian proficiency + propagation along prereq
  edges), **Squirrel AI** (10k+ knowledge points), **Duolingo Birdbrain**, **CZI/Anthropic
  Learning Commons** (a prereq knowledge graph exposed as an **MCP server** to Claude).

## 6. Agent architecture & skill design

- **Topology:** single-agent-with-tools **ReAct** loop as default; **Plan-and-Solve** front pass
  for the ordered pipeline (discover must precede digest); reserve **Tree-of-Thoughts** for the
  hardest curriculum/assessment decisions only (3–10× cost). **Reflexion** for post-session
  self-critique; **Self-Refine** for in-episode explanation polish; **MemGPT**-style tiered memory
  for multi-session continuity. **Voyager** is the blueprint for a self-authored, composable
  **skill library**.
- **Skill vs tool vs subagent:**
  - **Skill (Anthropic `SKILL.md`, progressive disclosure ~80 tok dormant / ~2k on activation):**
    reusable *capabilities* — `find-sources`, `digest-corpus`, `make-slides`, `make-mindmap`,
    `recommend-next`.
  - **Tool / MCP:** external API calls (OpenAlex, Semantic Scholar, arXiv, youtube-transcript) and
    deterministic ops (grade, store/read learner state).
  - **Subagent:** genuinely parallel work (multi-source search fan-out) or context isolation
    (digesting a huge doc).
- **Recommended:** **LangGraph state machine** for the deterministic teach/assess inner loop
  (reproducible, checkpointed, cheap) + agent-with-tools outer loop for the open-ended stages.
  Reuse `main`'s LangGraph + SqliteSaver, BKT-lite, concept_graph/graph_svg, grading seam, and the
  two-pane glass-box UI (already the embryo of the "full technical chain" frontend).

## 7. Cost governance (a first-class pillar)

Ranked by impact:
1. **Three-tier model cascade:** (a) BKT/Rasch routing decisions ≈ free; (b) cheap small model for
   QG / hints / grading / drafts; (c) frontier model **only** for cold-start concept explanation +
   flagged escalations. Routers: **RouteLLM** (ICLR 2025, ~2× saving at parity), **FrugalGPT**
   (up to 98%), **IRT-Router** (ACL 2025), BEST-Route. Confidence-threshold gate to escalate.
2. **Precompute "warm" domains offline; live only for cold domains** (demo's main domain is
   pre-digested; live-digest is the high-light, not the default).
3. **Caching:** prompt caching (`cache_control: ephemeral` on stable profile/skill/digest prefixes)
   + semantic result cache (~31% RAG hit) + per-document embedding cache.
4. **Cheap pre-filters before paid calls:** BM25 before embedding; metadata before full-text.
5. **Hard budget + metering:** per-session token budget, live cost meter (extend `ui/cost.py`),
   tool-loop caps, per-call observability (stage, model, tokens, cache hit). Alert at 80%.
6. **Skill progressive disclosure** keeps the base system prompt small even with 20+ skills.

## 8. Implied design decisions for the spec

1. **Concept graph = spine.** DIGEST = GraphRAG-style extraction + RefD/LLM prereq edges +
   confidence + a verify pass; precompute warm domains, live-digest cold ones behind a quality gate.
2. **Learner model = BKT/Rasch (catsim/jsCAT/girth), never LLM self-assessment.** Concrete library
   decision; LLM only reads mastery.
3. **Stages = skills over a LangGraph spine.** Outer agent loop chooses when to call discover /
   digest / make-artifact / recommend-next; teach/assess stay a deterministic graph.
4. **Multi-format = python-pptx + Marp + Mermaid/markmap**, via JSON-schema + thin-DSL pattern;
   reuse `concept_graph` for the mind-map.
5. **Assess = Bloom-leveled QG + overgenerate-and-rank distractors + SAQUET flaw gate + difficulty
   via LLM-sim/IRT (comparison prompting) + rubric grading with uncertainty escalation, 0–5 scale.**
6. **Cost = three-tier cascade + caching + precompute + first-class metering** from day one.
7. **Dual frontend = product Chat + Glass-box;** extend glass-box with source list, live digest-graph
   build, KT state, cost meter, artifact previews.

## 9. Follow-up actions (recorded, NOT executed)

- [ ] **Model needs to record (do not enable without approval):**
  - a **cheap/fast tier** for QG/hints/grading — `gpt-4o-mini` already fills this; evaluate a
    Haiku-class or DPO-tuned small tutor model later (record only).
  - a **retrieval re-ranker** — decide if needed beyond BM25 + free SPECTER.
  - embeddings: keep `text-embedding-3-small`.
- [ ] Confirm specific `26xx` arXiv IDs before formal citation in the spec/paper.
- [ ] Pick the demo's warm (pre-digested) domain(s) and the one cold domain for the live high-light.
- [ ] Evaluate `catsim` vs `jsCAT` vs `girth` for our learner-model backbone (Rasch + EAP).

## 10. Addendum — additional verified findings (high decision-value)

- **Assessment frequency / spacing (now concrete):** optimal first re-check ≈ **10–20% of the
  target retention window** (Cepeda et al. 2008, +64% recall vs massed). **MEMORIZE** (Tabibian
  et al., PNAS 2019, on 5.2M Duolingo pairs): review frequency should **scale inversely with
  current recall probability** — fixed "quiz every N" is demonstrably suboptimal. **Fast-forward
  over-practice** once per-KC `P(mastery) ≥ 0.95` (Xia et al. 2025). **Embed checks within
  instruction** (study-then-quiz ≈ 2.3× the gain of quiz-only). → Design: two-phase cadence
  (dense during acquisition, FSRS-spaced after mastery), gated by the BKT/Rasch mastery prob.
- **Feedback type matters:** **metacognitive** prompts ("why was that wrong?") beat affective and
  neutral feedback on *transfer* (Yin et al., npj Science of Learning 2025). → teach/reteach should
  include a metacognitive prompt, not just a correction.
- **Honest effectiveness ceiling (Responsible-AI framing):** ITS meta-analysis g ≈ **0.27**
  (modest); **worked-out examples are the single strongest moderator** (Leite/Zhang 2025). BKT
  reviews warn mastery flags are rarely validated against durable post-tests — so report mastery
  as an estimate, not a guarantee.
- **Distractor generation SOTA = small fine-tuned models beat GPT-4o** (reinforces the cheap-tier
  cost decision): **DiVERT** (MetaMath-Mistral-7B, EMNLP 2024) and **LookAlike** (51.6% vs DiVERT
  45.6%, BEA 2025) both beat GPT-4o on the primary metric; **DisGeM** is training-free (span
  masking); **D-GEN** open-sources 8B/70B distractor models. Evaluate distractors with **DISTO**
  / **DiVERT**'s error-label quality, not BLEU. **PlausibleQA** (SIGIR 2025) gives plausibility
  scores. → a small/cheap model is the right tier for QG + distractors; reserve frontier for
  cold-start explanation.
- **Knowledge-graph learning-path recommendation has converged** on: LLM-built **dual graph**
  (prerequisite + similarity) + KT mastery vector + **graph-constrained RL/ranking** for next-step
  (EDU-GraphRAG/KnowLP AAAI 2025; survey MDPI Electronics 15(1):238). For our scope, start with the
  simple, interpretable version: **hard prereq constraint + soft LLM/KT ranker** (RL is post-MVP).
- **Bloom level is linearly decodable from LLM activations** (arXiv:2602.17229, ~95% via linear
  probing) — supports Bloom-targeted prompting; but **fine-tuned discriminative classifiers
  (SVM/DistilBERT, 91–94%) beat zero-shot LLMs (~72%)** at *classifying* Bloom level on small data.

## Appendix — key tools/libraries shortlist

| Stage | Tool/lib | Note |
|---|---|---|
| Discover | OpenAlex, Semantic Scholar (SPECTER), arXiv, CORE, Wikipedia, youtube-transcript-api | all free |
| Discover | STORM / OpenScholar / PaperQA2 | agentic retrieval patterns |
| Digest | GraphRAG, RAPTOR | corpus→graph structuring |
| Learner model | catsim / jsCAT / girth | Rasch/IRT + EAP |
| Assess | SAQUET | item-writing-flaw gate |
| Slides | python-pptx, Marp, Pandoc | render layer |
| Mind-map | Mermaid, markmap | from concept_graph |
| Cost | RouteLLM / FrugalGPT / IRT-Router | model cascade |
| Orchestration | LangGraph (have it), Anthropic Skills, MCP | spine + skills + tools |
