# LitNavigator — Evidence-Based Improvement Review

*Compiled: 2026-06-21 · Branch under review: `feat/open-world-digest` · Status reference: OPEN-WORLD-STATUS.md (286 tests passing; 10/10 live e2e post-OW-3.1)*

**AI Disclosure:** This report was produced with AI-assisted research tools. The pipeline included AI-powered source verification, evidence synthesis, adversarial review, and report drafting. All foundation claims were verified against the `feat/open-world-digest` source (function-level citations recorded inline). Human oversight was applied throughout.

---

## Executive Summary

LitNavigator is an open-world adaptive research tutor: it discovers real sources for any goal, digests them into a cited prerequisite concept graph, and teaches/assesses adaptively under strict cost control (DISCOVER → DIGEST → ORIENT → TEACH → ASSESS → GRADE → artifact). The engineering is genuinely strong where it is tested **live**: the 10-scenario end-to-end suite reaches 100% source relevance and 4/4 non-English discovery after OW-3.1, persists grounded cited graphs, and runs at roughly $0.015–0.019 per scenario.

The central finding of this review is not that the *design* is unsound — every method LitNavigator names is a real, defensible technique — but that several **reviewer-facing per-step tables overstate the implementation relative to the project's own honest spec**. The single most load-bearing gap is the learner model: the primary keypoint path computes mastery with a hand-tuned bump rule (`kp_bump`) and a linear confidence counter (`kp_confidence = 0.30 × correct_obs`), yet the methods and storyboard tables cite plain "BKT — Corbett & Anderson 1995" with no "-lite" qualifier (Corbett & Anderson, 1995). Two more gaps are catchable by reading a single function: distractor generation is labelled "overgenerate-and-rank" but has no rank step (Scarlatos et al., 2024), and the "SAQUET" flaw gate screens ~3 structural flaws rather than SAQUET's ~19 item-writing flaws (Moore et al., 2024). On novelty, LitNavigator's real mechanism — a corpus reference-distance signal blended with an LLM judge-and-explain pass — is closest to ACE (Aytekin & Saygın, 2024), not to Liang et al.'s (2015) Wikipedia-link RefD; stating that lineage honestly *strengthens* the novelty claim rather than weakening it.

The prioritized recommendations are dominated by **cheap, honesty-restoring documentation fixes** (relabel BKT-lite; fix RouteLLM/ReAct venues; reframe RefD lineage) and a small set of dormant learning-science levers worth building (spaced retrieval delivery, an LLM item-writing-flaw gate). A recurring adversarial verdict applies across the recommendations: many are tagged against a metric (e.g., `objective_quality`, `quiz_validity`) they cannot causally move, because those metrics are structural or binary and the proposed change touches a different signal. The recommendations below carry those verdicts honestly.

**Keywords:** intelligent tutoring systems, knowledge tracing, prerequisite-relation extraction, concept-graph induction, LLM-assisted assessment, claim-vs-implementation integrity

---

## 1. Foundations Validity

Every foundation method LitNavigator cites is *sound* as a technique. The column that matters for an ICCSE submission is **correctly applied** — i.e., does the reviewer-facing claim match the code? The spec (§11/§12) is consistently honest ("BKT-lite," "mastery is an estimate"); the gaps are concentrated in the per-step **methods** (④a–④e) and **storyboard** (⑥) tables, which a reviewer reads first.

| # | Method (citation) | Sound | Correctly applied | Claim-vs-implementation note |
|---|---|---|---|---|
| 1 | **BKT** (Corbett & Anderson, 1995) | Yes | **No** | Primary keypoint path uses `kp_bump` (hardcoded gains: recall .25 / comprehension .40 / application .55; wrong −.20) + `kp_confidence = round(min(1, 0.30 × correct_obs))` — a heuristic, not a Bayesian posterior (`state.py`). A real `bkt_update()` (slip .10 / guess .20 / transit .30) exists but its constants are textbook-fixed, never EM-fitted, and it runs only on the **legacy** path. Spec says "BKT-lite"; methods ④d / storyboard ⑥ say plain "BKT." **Largest gap.** |
| 2 | **Rasch / 1PL IRT** (Rasch, 1960; "Take Out Your Calculators," 2026) | Yes | **No** | `irt_b` is set by a one-shot *weaker*-LLM student simulator — which **is** current best practice and correctly applied (weaker models reproduce student error distributions, r up to .82). But `irt_theta` is a schema column never written or read: no online ability estimation. Credit the simulator; flag the unfitted theta. |
| 3 | **RefD** (Liang et al., 2015) | Yes | **No** | `refd.py` is chunk-term co-occurrence / reference-distance asymmetry over the corpus's *own* chunks — not Liang's Wikipedia link-reference graph with relatedness weights. Spec hedges "RefD-style"; storyboard/methods cite bare "RefD — Liang 2015." ACE (Aytekin & Saygın, 2024) is the precise precedent for the actual structural-score + LLM-judge pattern. The two-signal design itself worked live (RefD recovered `in_context_learning → agentic_reasoning` the judge alone rejected). |
| 4 | **GraphRAG** (Edge et al., 2024) | Yes | **No** | Extraction is tagged "GraphRAG-style," but GraphRAG is query-focused *summarization* over an entity graph — not concept extraction or prerequisite induction. Buzzword mismatch. Cite the concept-map / prerequisite-mining survey (e.g., a recent ACM Computing Surveys prerequisite-relation survey) instead. |
| 5 | **SPECTER** (Cohan et al., 2020) | Yes | **Yes** | Substituted by `text-embedding-3-small` cosine in the rerank — and the substitution is **disclosed** in both spec and methods. Correctly handled; add the same note to the storyboard table for consistency. |
| 6 | **BM25** (Robertson & Zaragoza, 2009) | Yes | **Yes** | Keyword prefilter before embedding rerank (`rank.py`) — a standard, correctly applied retrieval cascade. No issue. |
| 7 | **FrugalGPT** (Chen et al., 2023) | Yes | **Yes** | Cheap→frontier cascade with confidence-gated escalation. LitNavigator's deviation (route on *pedagogical-error* cost near the mastery band, not token cost) is a defensible, well-argued improvement, not a misuse. |
| 8 | **RouteLLM** (Ong et al., 2025) | Yes | **Yes (with venue error)** | Correctly applied as routing inspiration. **Venue error:** methods say "RouteLLM (ACL 2025)"; it is **ICLR 2025**. The escalation trigger is a hand-set threshold (`CONF_MIN = 0.6` + band), not RouteLLM's *learned* router — an honest "inspired-by." |
| 9 | **SAQUET** item-flaw gate (Moore et al., 2024) | Yes | **No** | `flaw_gate` is structural-only (~3 checks: empty stem, <2 distinct distractors, distractor == answer). SAQUET screens ~19 item-writing flaws (cueing, implausible/heterogeneous distractors, all-of-the-above, negative stems, grammatical clues). The docstring says "SAQUET-style"; the methods table drops that scoping. |
| 10 | **Overgenerate-and-rank distractors** (Scarlatos et al., 2024) | Yes | **No** | `make_distractors` overgenerates ~6, drops the answer, dedups, and takes the **first n** — there is **no rank step**. Scarlatos et al. are explicit that ranking by student plausibility is what makes the method work. The "and-rank" claim is currently false. |
| 11 | **FSRS** spaced repetition (Open Spaced Repetition, 2023) | Yes | **No** | `spacing.py` is FSRS-lite (interval = 1/(1−mastery), ×2 fast-forward at ≥0.95), no fitted DSR stability/lapse state. Worse, `review_queue` items are enqueued but **never delivered** before teaching — the retrieval benefit is dormant. |
| 12 | **Specialised KT > LLMs / "never self-judge"** (Bhattacharyya et al., 2026) | Yes | **No (framing)** | The "never LLM self-judge" principle is correctly adopted and well-grounded. But the source shows LLM-KT *narrowly top* (72.8% vs SAKT 72.7%); the durable claim is *comparable-or-better accuracy at 600–12,000× lower cost/latency*, not universal accuracy dominance. Soften to avoid a reviewer rebuttal. |
| 13 | **ReAct + Plan-and-Solve** (Yao et al., 2023; Wang et al., 2023) | Yes | **No** | Outer-loop *topology* matches, but the plan is implicit branching — no logged plan artifact — and reteach has no Reflexion-style error memory (a `MAX_RETEACH` counter flips strategy). **Venue:** methods cite "ReAct — Yao et al. 2022"; it is the 2022 preprint, **ICLR 2023**. |
| 14 | **Worked-example effect / expertise reversal** (Barbieri et al., 2023; Sweller & Kalyuga) | Yes | **No** | `worked_example` is a static label at mastery < 0.35 (+ a "concise" label for experts) — no fading ladder (full → completion → full problem). The durable benefit comes from *fading*; expertise reversal means an unfaded example *hurts* advanced learners. Principle named, mechanism absent. |
| 15 | **Interleaved practice** (Brunmair & Richter, 2019) | Yes | **No** | Interleaving is effectively absent — the route is strictly prereq-ordered/blocked. `concept_edges.similarity` already gives a principled trigger (interleaving helps only for confusable material, g ≈ 0.42), but the lever is unused. |
| 16 | **Testing/retrieval-practice effect** (Roediger & Karpicke, 2006; Yang et al., 2021) | Yes | **No** | Used for *grading*, not for memory *strengthening*: `review_queue` + `retention_log` exist but no spaced retrieval probe is delivered before new teaching. Data layer built; lever dormant. |
| 17 | **Mayer multimedia/coherence** (Mayer, 2009) | Yes | **Yes** | Applied in `teach_kp` and the artifact renderers (anti-verbatim Cornell notes, coherent slides). Reasonable application; no overstatement found. |
| 18 | **Bloom-leveled question generation** (Scaria et al., 2024) | Yes | **No** | `assess_next` passes a one-line per-level spec but no Bloom *definition* and no exemplars. Scaria et al. find adequate info + exemplars enable the higher rungs; comprehension/application items are the weakest link. Under-applied at the prompt level. |
| 19 | **Mastery threshold / mastery learning** (Zhang et al., 2025; Winget & Persky, 2022) | Yes | **No** | `KP_MASTERY_THRESHOLD = 0.75` is lenient vs the mastery-learning literature (≈0.95 standard; ≈0.98 for transfer). Advancing at 0.75 risks under-mastery and is neither surfaced nor justified against a retention probe. The honest g ≈ 0.27 ITS-gain framing elsewhere *is* correctly applied. |

**Pattern.** 13 of 19 foundations are *sound but not (yet) correctly applied as labelled*, and almost all of those are **documentation overstatements**, not broken code. The spec is honest; the per-step demo tables are not. The cheapest, highest-integrity win is to make the reviewer-facing tables match the spec.

---

## 2. Core-Novelty SOTA — Prerequisite / Concept-Graph Induction

**Where the field is.** Prerequisite-relation extraction has moved from local pairwise scoring toward **global, multi-relation optimization**, while the field's own surveys stress two caveats LitNavigator should lean into: prerequisite *ordering is pedagogy-dependent* (there is no single ground truth), and *open-web/live extraction is largely unvalidated* (Zhang et al., 2025; Bian, 2025).

**LitNavigator's actual mechanism, stated honestly.** The closest published analogue is **ACE** (Aytekin & Saygın, 2024) — a structural/embedding score blended with an LLM judge-and-explain pass — **not** Liang et al.'s (2015) Wikipedia-link RefD. LitNavigator is *RefD-inspired* (corpus reference-distance over its own chunks) plus a zero-shot `gpt-4o` judge with a RefD-rescue path, and it **adds** a frontier verify pass, an edge-accuracy spot-check, and a similarity fallback on top of the ACE pattern. That additive layer is a **genuinely citable contribution once the lineage is stated** — the honest framing is the stronger one.

**Where LitNavigator trails the frontier.**
1. **No global-consistency / cycle-breaking pass.** Edges are scored locally/pairwise, whereas global multi-relation optimization is the current accuracy frontier (e.g., GKROM, AAAI 2025; DGCPL, IJCAI 2025). The concrete symptom: a single-source digest yields **0 surviving prerequisite edges** (OPEN-WORLD-STATUS, OW-5.1).
2. **Open-web edge accuracy is untested.** Every SOTA accuracy number is closed-corpus on dense graphs; LitNavigator's open-web edge accuracy is unmeasured (spec risk A) — and single-source sparsity is a failure mode dense-graph SOTA never faces.
3. **Path planning is furthest behind.** Pxplore (WWW 2026) is goal-conditioned and RL-trained over a structured learner state; LitNavigator's `recommend-next` is a deterministic prereq filter + hand-ranked tie-break, and is still **unbuilt** (OW-6).

**The strongest defensible position.** Do **not** borrow closed-corpus benchmark numbers. Lean into the alignment between LitNavigator's glass-box, soft-constraint, similarity-fallback design and the survey's own caveats (no single ground truth; open-web unvalidated), and **report a live, self-measured edge-accuracy number** from the edge-accuracy spot-check the system already emits. That converts risk A from a weakness into a differentiator: LitNavigator measures the thing the field admits is unmeasured.

---

## 3. Prioritized Recommendations

Ordered by score. Every item carries the adversarial verdict; a recurring theme is **metric mismatch** — a real improvement filed against a metric it cannot causally move (the cargo-cult tell).

| ID | Stage | Hypothesis (trimmed) | Metric it moves | Effort | Risk | Demo-visible | Score | Adversarial verdict | Citation |
|---|---|---|---|---|---|---|---|---|---|
| **R1** | learner-model | Relabel the keypoint mastery mechanism as **"BKT-lite bump rule (hand-tuned; not a fitted BKT)"** in methods ④d + storyboard ⑥; reserve bare "BKT (Corbett & Anderson 1995)" for the legacy `bkt_update` path. | claim-integrity *(re-tag from objective_quality)* | S | low | yes | **9** | **Revise.** Doc-honesty fix is real and verified; **scope it to the keypoint path** (the legacy path genuinely runs BKT and a blanket rename would *under*-claim it). Re-tag away from `objective_quality` (label has no causal path to objective generation). Drop the 2603.02830 citation here (decorative). Drop/defer the pyBKT follow-on (retention_log is N≈1 sparse single-probe data — fitting BKT on it is statistically meaningless). | Corbett & Anderson (1995) |
| **R3** | assess | **Deliver the spaced-retrieval probes already enqueued:** pop due `review_queue` items as low-stakes retrieval quizzes before new teaching, logging predicted-vs-actual. | delayed-probe accuracy / calibration error *(re-tag from reteach_recovery)* | M *(not S)* | low | yes | **8.5** | **Revise.** Citations on-point; feature worth building. But `reteach_recovery` measures an *in-concept* reteach loop that never reads `review_queue`/`retention_log` — session-start spacing cannot move it (and it is near-saturated at 1.0). Only the *producer* half (`schedule_review`) is wired; `due_probes`/`log_retention` have no consumers. Needs a new probe node + routing + UI: not S. "Predicted" is uncalibrated by construction (mastery is the bump+linear gate, not P(recall)). | Roediger & Karpicke (2006); Yang et al. (2021) |
| **R4** | digest | **Reframe edge-signal citation** from bare "RefD (Liang 2015)" to "RefD-inspired corpus reference-distance + LLM judge-and-explain (cf. ACE, 2024)"; add the ACM 2025 prereq survey as framing anchor; drop/qualify "GraphRAG-style." | citation-honesty / novelty-framing *(re-tag from objective_quality)* | S | low | no | **8** | **Revise.** Attribution-tightening is verified and worth doing (methods/storyboard overclaim vs `refd.py`; "GraphRAG-style" is cargo-cult). **But** it is documentation-only and demo_visible:false — it cannot move `objective_quality` (touches zero objective-producing code). **Verify the ACE/JEDM and ACM-survey citations independently before importing** them, or you trade one known overclaim for new unverified ones. | Liang et al. (2015); Aytekin & Saygın (2024); Edge et al. (2024) |
| **R5** | assess | **Upgrade `flaw_gate`** from structural-only to an LLM-judge pass against an explicit item-writing-flaw checklist, making "SAQUET-style" honest. | new IWF-violation flaw-rate scorer *(re-tag from quiz_validity)* | M | low | yes | **7.5** | **Revise.** Both citations verified; the claim-vs-impl gap is real and the fix improves actual item quality. **But** `quiz_validity` is a structural scorer already at 1.0 — an IWF judge changes none of its fields, so it cannot move that metric (the loop-changelog already deferred R5 for exactly this). Either add a live IWF-rate scorer or label it "live-only / accepted by inspection." Caveat: SAQUET's 94% is *detection* accuracy, not evidence of end-to-end learner-validity gain; the structural gate currently never fires on live items, so marginal value is real but unquantified. | Moore et al. (2024); Distractor Generation Survey (2024) |
| **R6** | grade | **Drive `kp_bump` from the existing 0–5 partial-credit score** (not the binary flag) and add a component-extraction step before scoring. | avg_mastery_delta *(NOT grading_acc as tagged)* | M | med | yes | **7.5** | **Revise.** Citations on-point (component-extraction → QWK; 0–5 maximizes human–LLM alignment). **But** `grading_acc` is binary classifier accuracy on a 16-case all-binary golden set with **zero partial-credit cases** — driving mastery from `score_0_5` feeds *mastery*, invisible to `grading_acc`. Also a convention conflict: CLAUDE.md mandates mastery be rule-computed, not LLM-emitted. To move the metric: wire component-extraction into the grade path *and* rebuild the golden set with partial-credit cases. Score overstated at 7.5. | AutoSCORE (2025); Grading-Scale Impact (2026); Rubric-Conditioned Grading (2026) |
| **R8** | discover | **Fix venue/framing for submission:** RouteLLM = ICLR 2025 (not ACL); ReAct = ICLR 2023 (2022 preprint); soften "specialised KT always beats LLMs" to "comparable-or-better at 600–12,000× lower cost/latency"; add the SPECTER→`text-embedding-3-small` note to the storyboard. | objective_quality (factual defensibility) | S | low | no | **7** | **Keep.** All three citations verified against arXiv; venue errors are trivially reviewer-checkable; causal path to submission defensibility is direct, not cargo-cult. Two notes: the SPECTER substitution note is *already* in storyboard line 16 + methods line 27 (mostly redundant); and the rec should be **widened** to also soften the BKT/IRT mastery overclaim (R1's gap) so venue-fixing isn't inconsistent with leaving the bigger overclaim standing. | Ong et al. (2025); Yao et al. (2023); Bhattacharyya et al. (2026) |

**Reading the verdicts.** Five of six surviving recommendations were returned **revise**, all for the same structural reason: the *change* is legitimate but the *metric it was sold against* is structural, binary, or already saturated, so the offline eval is blind to it. The disciplined move is to (a) ship the cheap honesty fixes (R1, R4, R8) now, (b) re-tag R3/R5/R6 to metrics that can actually observe them and build the corresponding scorers, and (c) treat R1's BKT-lite relabel as the load-bearing one — it is the gap a reviewer citing the KT literature will scrutinize first.

---

## 4. Limitations & Honesty Notes

- **This review audits documentation-vs-code, not learning outcomes.** No claim here establishes that LitNavigator produces durable learning. The spec is candid about this (risk B): mastery is an *estimate*, ITS gains are modest (g ≈ 0.27), and the delayed retention probe is an internal-validation signal, not proof.
- **The metrics this review references are mostly structural or near-saturated.** `quiz_validity` ≈ 1.0, `grading_acc` runs on 16 all-binary cases, `reteach_recovery` falls back to 1.0 with no reteach. Several "improvements" are genuinely unmeasurable by the current offline eval — that is itself a finding, not a dodge.
- **Open-web edge accuracy is unvalidated (spec risk A).** LitNavigator cannot claim benchmark-grade prerequisite accuracy; it should report a *live self-measured* edge-accuracy number and frame the open-web setting as the differentiator, since closed-corpus SOTA never faces single-source 0-edge sparsity.
- **Some proposed citations are unverified.** The ACE (JEDM 2024) and ACM Computing Surveys 2025 prerequisite-survey references are the *correct kind* of precedent for the actual mechanism, but the reviewer flagged that they are not present in the repo and were not independently confirmed in this pass. They must be verified to exist and match the code before being imported into the submission — fixing one overclaim with an unverified citation is a net loss. The remaining References below are well-established works whose existence is not in dispute, but every reference should be re-confirmed against its DOI/venue before submission.
- **Two literal docstring-vs-code lies remain until R4/R5 ship:** `make_distractors` ("overgenerate-and-rank" with no rank) and `flaw_gate` ("SAQUET-style" screening ~3 of ~19 flaws). A reviewer can catch each by reading one function.
- **Recommendation R1's optional pyBKT follow-on is deferred, not endorsed:** the `retention_log` holds sparse single-probe data from N≈1 demo runs; fitting BKT on it would make the claim *less* honest, not literally true. Defer until multi-learner data exists.

---

## References

Aytekin, Ç., & Saygın, Y. (2024). ACE: A concept-graph induction approach blending structural scoring with LLM judge-and-explain. *Journal of Educational Data Mining, 16*(2). *[Verify venue/DOI before submission.]*

Barbieri, C. A., et al. (2023). The worked-example effect: A meta-analysis. *Educational Psychology Review, 35*, Article 11.

Bhattacharyya, A., et al. (2026). *Faster, cheaper, more accurate: Specialised knowledge-tracing models outperform LLMs* (arXiv:2603.02830). arXiv.

Bian, J. (2025). *A survey of prerequisite-relation learning and concept-graph induction* (arXiv:2510.20345). arXiv.

Brunmair, M., & Richter, T. (2019). Similarity matters: A meta-analysis of interleaved learning and its moderators. *Psychological Bulletin, 145*(11), 1029–1052.

Chen, L., Zaharia, M., & Zou, J. (2023). *FrugalGPT: How to use large language models while reducing cost and improving performance* (arXiv:2305.05176). arXiv.

Cohan, A., Feldman, S., Beltagy, I., Downey, D., & Weld, D. S. (2020). SPECTER: Document-level representation learning using citation-informed transformers. *Proceedings of ACL 2020*.

Corbett, A. T., & Anderson, J. R. (1995). Knowledge tracing: Modeling the acquisition of procedural knowledge. *User Modeling and User-Adapted Interaction, 4*(4), 253–278.

Edge, D., et al. (2024). *From local to global: A GraphRAG approach to query-focused summarization* (arXiv:2404.16130). arXiv.

Liang, C., Wu, Z., Huang, W., & Giles, C. L. (2015). Measuring prerequisite relations among concepts. *Proceedings of EMNLP 2015* (pp. 1668–1674). ACL D15-1193.

Mayer, R. E. (2009). *Multimedia learning* (2nd ed.). Cambridge University Press.

Moore, S., et al. (2024). SAQUET: An automatic question usability evaluation toolkit. *Proceedings of AIED 2024* (arXiv:2405.20529).

Ong, I., et al. (2025). RouteLLM: Learning to route LLMs with preference data. *International Conference on Learning Representations (ICLR) 2025* (arXiv:2406.18665).

Open Spaced Repetition. (2023). *Free Spaced Repetition Scheduler (FSRS): The DSR memory model.* (Ye et al., 2022–2023.)

Rasch, G. (1960). *Probabilistic models for some intelligence and attainment tests.* Danmarks Pædagogiske Institut.

Robertson, S., & Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333–389.

Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning: Taking memory tests improves long-term retention. *Psychological Science, 17*(3), 249–255.

Scaria, N., et al. (2024). Automated educational question generation at different Bloom's skill levels using LLMs. *Proceedings of AIED 2024* (arXiv:2408.04394).

Scarlatos, A., et al. (2024). Improving automated distractor generation for math multiple-choice questions. *Proceedings of NAACL 2024 BEA Workshop.*

*Take out your calculators: Difficulty estimation with deliberately weaker LLM simulators.* (2026). (arXiv:2601.09953). arXiv.

Winget, M., & Persky, A. M. (2022). A practical review of mastery learning. *American Journal of Pharmaceutical Education, 86*(10), Article 8906.

Yang, C., et al. (2021). Testing (quizzing) boosts classroom learning: A systematic and meta-analytic review. *Psychological Bulletin, 147*(4), 399–435.

Yao, S., et al. (2023). ReAct: Synergizing reasoning and acting in language models. *International Conference on Learning Representations (ICLR) 2023* (arXiv:2210.03629, 2022 preprint).

Wang, L., et al. (2023). Plan-and-Solve prompting: Improving zero-shot chain-of-thought reasoning by large language models. *Proceedings of ACL 2023.*

Zhang, X., et al. (2025). A survey of prerequisite-relation extraction and concept-graph construction for education. *ACM Computing Surveys, 57*(11). *[Verify volume/issue before submission.]*

Zhang, Y., et al. (2025). How much mastery is enough mastery? *Proceedings of EDM 2025.*

*Supporting works cited inline:* AutoSCORE (arXiv:2509.21910, 2025); Grading-scale impact on LLM-as-a-judge (arXiv:2601.03444, 2026); Rubric-conditioned LLM grading (arXiv:2601.08843, 2026); Distractor generation in multiple-choice tasks: A survey (arXiv:2402.01512, 2024); GKROM (AAAI 2025); DGCPL (IJCAI 2025); Pxplore (WWW 2026). *Each should be DOI/venue-verified before submission.*

---

*Word count: ~2,650. Mode: standalone compile (no downstream finalizer). Unresolved issues: (1) ACE/JEDM, ACM-survey, and the global-optimization SOTA citations (GKROM/DGCPL/Pxplore) require independent existence/venue verification before submission — flagged as `[VERIFY]` inline; (2) several recommendation metrics require new scorers before the offline eval can observe the proposed changes.*

**Note on citation format:** This report uses APA 7.0 author-year in-text citations and a References list as requested. The machine-extractable citation markers and Material Passport described in the compiler contract were not emitted because no corpus context with `citation_key` slugs was provided in this invocation, and the requested deliverable is a human-readable APA report; emitting fabricated slugs would violate the corpus-only-slug rule.
