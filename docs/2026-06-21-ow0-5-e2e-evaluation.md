# OW-0 → OW-5 End-to-End Evaluation — 10 Diverse Live Scenarios

**Date:** 2026-06-21 · **Branch:** `feat/open-world-digest` · **Harness:** `litnav/evaluation/e2e_scenarios.py`
**Raw per-step logs:** [`docs/e2e-logs/scenario-01..10-*.md`](e2e-logs/) · **Machine data:** [`docs/e2e-logs/summary.json`](e2e-logs/summary.json)
**Provider:** OpenAI live (`gpt-4o-mini` cheap · `gpt-4o` judge · `text-embedding-3-small`) · strict mode · every call metered.

## What this is
Ten learning scenarios, each varying **all five dimensions** — goal, intended depth, the learner's prior
knowledge, **language**, and discipline — run end-to-end through the real orchestrators:
DISCOVER (OW-3) → DIGEST (OW-2/1) → goal-elicit + ASSESS (OW-4) → make-artifact (OW-5), over the
metered cost spine (OW-0). This is a **documented assessment of real performance**, not a pass/fail gate.

| # | Domain | Language | Depth | Prior knowledge |
|--|--|--|--|--|
| 1 | ML / generative (diffusion) | English | mastery | ML practitioner |
| 2 | Biology / CRISPR | 中文 | survey | bio undergrad |
| 3 | Distributed systems / Raft | English | functional | backend engineer |
| 4 | Physics / quantum error correction | English | survey | physics undergrad |
| 5 | Finance / Black-Scholes | Español | mastery | finance novice |
| 6 | Biochemistry / mRNA vaccines | English | functional | layperson |
| 7 | NLP / transformer attention | 中文 | mastery | CS grad |
| 8 | Economics / nudges | English | survey | layperson |
| 9 | ML / RLHF | English | functional | ML engineer |
| 10 | Graph ML / GNNs | Français | survey | data scientist |

## Headline
**Mechanically the pipeline is green end-to-end (9/10 ran fully; 1 aborted at discovery), but *topical
correctness* hinges entirely on DISCOVER picking a relevant source — and it does so only ~44% of the
time, and 0/4 for non-English goals.** Every downstream stage faithfully processes whatever source it is
handed, so a wrong source yields a fluent, well-graded, correctly-formatted, fully-cited tutoring
session **about the wrong topic** (e.g. the Chinese "CRISPR" request was taught as *disruptive
technology*; "Raft consensus" as the film *Megalopolis*). The open-world plumbing built in OW-0..5.1 —
metering, persistence, grounding, format selection, goal classification — held up across every domain
and language. The bottleneck is **source discovery quality**, not the teaching machine.

## Update — post PR-#6 merge re-run (same 10 scenarios)
After merging PR #6 (jing-yen: evidence-fed prereq judge, edges LLM similarity judge, extract kp_id
coercion + objective prompt) on top of our OW-5.1 fixes, the **digest quality layer jumped**:

| Metric | Pre-merge | Post-merge (PR #6 + OW-5.1) |
|--|--|--|
| prereq edges survive (>0) | **1/9** | **9/9** ✅ |
| edge_accuracy | ≈0.0 | 0.5–1.0 |
| keypoints present (>0) | 3/9 | **9/9** ✅ |
| concepts persisted · artifacts grounded+cited | 9/9 | 9/9 (held) |
| goal→depth match | 9/9 | 9/9 (held) |
| cost / full scenario | ~$0.0034 | **$0.0169 (~5×)** · total $0.15 |

- **A7 (prereq survival) and A10 (keypoint yield) → CLOSED** by the merge. The evidence-fed judge + kp_id coercion did it.
- **A5 (source relevance) and A6 (non-English) → UNCHANGED** — PR #6 touched no discover code. Top sources still wrong for #1 (physics diffusion), #2/#7 (disruptive-tech for Chinese), #3 (Megalopolis film), #10 (French neuroscience); Spanish still 0 sources. **This is OW-3.1's target.**
- **New: A11 (cost) — digest cost ~5× ($0.0034→$0.0169/run)** from the `digest_sim_judge` running on frontier `gpt-4o`. Recorded action: evaluate moving the *similarity* judge to the cheap tier (prerequisite judging can stay frontier).

## Per-stage performance

### OW-0 Cost spine — ✅ flawless
9/9 completed scenarios `was_live=True`, every call metered. **$0.0026–$0.0042 per full scenario; total
≈ $0.031 for all 10.** Digest dominates wall-clock (30–44 s, the `gpt-4o` judge + extraction); discover
2.6–7.6 s; artifacts 3.5–6.5 s. No budget breaches.

### OW-3 DISCOVER — ⚠️ the weak link
Top-ranked source actually digested, scored for relevance to the goal:

| Relevant ✅ (4/9) | Wrong ❌ (5/9) |
|--|--|
| #4 QEC → "Quantum Error Correction For Dummies" | #1 diffusion-models → "**Anomalous diffusion**" (physics, not ML) |
| #6 mRNA → "mRNA vaccines in disease prevention" | #3 Raft → "**Megalopolis (film)**" (Wikipedia) |
| #8 nudges → "Nudging in education" | #2 CRISPR(中) → "颠覆性技术研究" (disruptive tech) |
| #9 RLHF → "Reinforcement learning from human feedback" | #7 attention(中) → "颠覆性技术研究" (same generic paper) |
| | #10 GNN(fr) → "PRÉDISPOSITION…CERVEAU" (neuroscience) |

- **Term ambiguity** mis-resolves ("diffusion", "raft") — authority can be high on the wrong source (#1 auth 0.88). Relevance rerank doesn't dominate authority/ambiguity enough.
- **Wikipedia adapter is noisy** — returned a film for "Raft".
- **Non-English is broken (0/4):** Español → **0 sources** (pipeline aborts); 中文 → a *single* low-authority generic paper (same one for two different Chinese goals); Français → off-domain. English-biased indices (OpenAlex/arXiv) + **no query translation**.
- Intent classification itself is plausible across all languages (cutting-edge/crash-course/applied/systematic).

### OW-2 DIGEST — ✅ persistence solid; ⚠️ thin-evidence quality
- **Persistence (OW-5.1 fix holding):** 9/9 persisted 6–8 concepts to the DB; `kp_evidence_resolves=True` everywhere. No silent drops.
- **Faithful but GIGO-bound:** concepts are accurate *to the source* — so a wrong source gives on-source / off-goal concepts ("visionary architecture" from the Megalopolis page).
- **Prerequisite edges barely survive on a single source:** 0 prereq in 8/9 (only #4 got 2; edge_accuracy 0.29). Single-source digests can't support hard prerequisites — needs multi-source / richer evidence (the known A1 signal, now confirmed at scale).
- **Keypoint extraction is non-deterministic:** 0 keypoints in 6/9, 7–8 in 3/9. Artifacts stay grounded anyway via the OW-5.1 source-pool fallback.

### OW-4 TEACH / ASSESS — ✅ most robust component
- **Goal→depth classification: 9/9 correct**, fully language-agnostic (中文 "深入掌握"→mastery, "快速概览"→survey; fr "introduction"→survey).
- Distractors 3/3 with flaw-gate pass 9/9; metered grade works; strategy policy maps expertise→strategy correctly (expert→concise, novice→overview, intermediate→worked_example).
- **Inherits the wrong-source problem:** quiz stems reflect the digested (sometimes wrong) concept ("What is visionary architecture?" for the Raft session). Grading only exercised the correct-answer path here (discrimination is covered by `verify_teach_assess`).

### OW-5 MAKE-ARTIFACT — ✅ structurally perfect; ⚠️ two gaps
- 9/9 notes + mindmap **non-empty, grounded, citations resolve** (OW-5.1 grounding holding across every scenario).
- **Format selection 9/9 correct** per goal_type (mastery→combination, survey→mindmap, functional→worked_example).
- **Citations always collapse to a single `c0`** — discovered full text isn't sub-chunked, so there's only one citable chunk per source.
- **No output-language control:** concept names follow the source (中文/fr), but generated cues/summaries default to **English** — a mixed-language artifact for non-English learners.

## Scenario outcomes (one line each)
| # | Discover | Source relevant? | Concepts | Keypts | Prereq | Goal match | Artifacts | $ |
|--|--|--|--|--|--|--|--|--|
| 1 diffusion (en) | 6 src | ❌ physics | 8 | 0 | 0 | ✅ | ✅ cited | .0037 |
| 2 CRISPR (中) | 1 src | ❌ disruptive-tech | 8 | 8 | 0 | ✅ | ✅ cited | .0037 |
| 3 Raft (en) | 3 src | ❌ film | 8 | 8 | 0 | ✅ | ✅ cited | .0028 |
| 4 QEC (en) | 6 src | ✅ | 8 | 0 | 2 | ✅ | ✅ cited | .0042 |
| 5 Black-Scholes (es) | **0 src** | — abort | — | — | — | — | — | ~0 |
| 6 mRNA (en) | 6 src | ✅ | 7 | 7 | 0 | ✅ | ✅ cited | .0031 |
| 7 attention (中) | 3 src | ❌ disruptive-tech | 8 | 0 | 0 | ✅ | ✅ cited | .0036 |
| 8 nudges (en) | 6 src | ✅ | 7 | 0 | 0 | ✅ | ✅ cited | .0029 |
| 9 RLHF (en) | 3 src | ✅ | 6 | 0 | 0 | ✅ | ✅ cited | .0026 |
| 10 GNN (fr) | 6 src | ❌ neuroscience | 8 | 0 | 0 | ✅ | ✅ cited | .0040 |

## Bugs / gaps, ranked

| Sev | Where | Finding | Evidence | Proposed fix |
|--|--|--|--|--|
| **P0** | OW-3 | Source relevance ~44%; ambiguous terms + noisy Wikipedia pick off-topic top source | #1,#3,#10; auth 0.88 on wrong #1 | relevance-gate the top source (LLM/embedding "is this source about the goal?" filter before digest); weight relevance ≫ authority; demote bare-title Wikipedia hits; expand query with goal context |
| **P0** | OW-3 | Non-English discovery broken (0/4): es=0 sources, 中文=1 generic, fr=off-domain | #2,#5,#7,#10 | translate/normalize the query to English for indices (or add language param to adapters); keep teaching in the user's language |
| **P1** | OW-2 | Prereq edges don't survive single-source digest (edge_accuracy≈0) | 8/9 with 0 prereq | multi-source digest for the goal slice (digest top-k, not top-1); lower prereq bar or accumulate evidence across sources |
| **P1** | OW-5/4 | No output-language control — cues/summaries default to English for non-English goals | #2 notes (English cues on 中文 concepts) | thread goal language into renderer + teach prompts ("respond in <lang>") |
| **P2** | OW-5 | Citations collapse to single `c0` — full text not sub-chunked | all 10 | sub-chunk fetched full text into c0..cN at digest time |
| **P2** | OW-2 | Keypoint extraction non-deterministic (0 in 6/9) | summary | strengthen the extraction prompt to always emit ≥1 keypoint/concept; or synthesize a keypoint from the concept+chunk |
| **P3** | harness | Windows GBK console crashed multilingual logging (now fixed) | run 1 #7,#10 | `sys.stdout.reconfigure(utf-8)` (done) |

## What held up (the wins)
- **OW-0** metering + liveness: 100% live, fully accounted, ~$0.003/scenario.
- **OW-5.1 persistence + grounding**: 9/9 concepts persisted; 9/9 artifacts non-empty with resolving citations — the bug class that was invisible to the old gates is now closed and stays closed across 10 fresh topics.
- **OW-4 goal classification + format selection**: 9/9 each, language-agnostic — the "understand the learner" layer is the strongest part.
- **Faithfulness**: no hallucinated citations; every artifact cited a real chunk; digest never invents beyond its (sometimes wrong) source.

## Verdict & recommended priority
The teaching machine (OW-2 persistence, OW-4, OW-5) is **production-quality on good input**. The open-world
promise is currently **gated by discovery quality**. Before OW-6 (frontend) makes this learner-facing, the
highest-leverage work is **OW-3.1: a source-relevance gate + non-English query handling** (P0×2), then
**multi-source digest** (P1) to recover prerequisite structure. These are recorded as actions; none require
a new model tier — `gpt-4o-mini` + `gpt-4o` + embeddings remain adequate (a relevance gate is one more cheap call).
