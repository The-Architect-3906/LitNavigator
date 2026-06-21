<div align="center">

# 🧭 LitNavigator — Open-World Edition

### Give it any learning goal. It finds the most suitable real sources, digests them into a teachable concept map, and tutors *you* through it — adaptively, grounded in the literature, under strict cost control.

![Status](https://img.shields.io/badge/open--world-OW--0..5%20complete%20(live)-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Agent](https://img.shields.io/badge/agent-LangGraph%20%2B%20ReAct-black)
![Live](https://img.shields.io/badge/validation-live--first-orange)
![ICCSE 2026](https://img.shields.io/badge/ICCSE%202026-Agentic%20AI%20Competition-purple)

</div>

---

## The gap nobody fills

> *You have a question about a research field. Who goes and gets the right papers, turns them into a syllabus, and then teaches it to you — adapting as you stumble?*

| | Models you | Adaptive teach/test/reteach | Prereq sequencing | From living literature | **Finds its own sources** | Curriculum source |
|:--|:--:|:--:|:--:|:--:|:--:|:--|
| Elicit / SciSpace | ✗ | ✗ | ✗ | ✓ | ✓ | — |
| NotebookLM | ✗ | ✗ | ✗ | ✓ (you upload) | ✗ | — |
| Khanmigo / LearnLM | ✓ | ✓ | ✓ | ✗ | ✗ | human-authored |
| **LitNavigator (open-world)** | ✓ | ✓ | ✓ | ✓ | ✓ | **discovered + digested live** |

The closed-world edition (M0–M3) tutored from a *curated* paper pack. The **open-world** edition removes the boundary: it **discovers** sources for any goal and **digests** them into the concept graph on demand.

---

## How it works

The **open-world layer (blue → green) builds the concept graph on demand**, then hands it to the
**inner teaching loop (purple, LangGraph + checkpointed)** — the same orient → teach → assess → route
machine as the curated edition — and finally to **artifacts (pink)** and **next-step (grey)**. Every
LLM/embedding call goes through the **one metered router (amber)**.

```mermaid
flowchart TD
    G([🎯 Your learning goal])

    %% ===================== OPEN-WORLD: build the graph on demand =====================
    subgraph DISC [find-sources · DISCOVER · OW-3]
      direction TB
      FS1[intent classify\ngoal → survey · applied · cutting-edge]
      FS2[OpenAlex + Wikipedia adapters\nmetadata + authority]
      FS3[BM25 prefilter → embedding-cosine rerank\n+ authority + dedup]
      FS4[top-k arXiv full text]
      FS1 --> FS2 --> FS3 --> FS4
    end
    subgraph DIG [digest-corpus · DIGEST · OW-2]
      direction TB
      DG1[extract concepts + keypoints\ncheap · temp 0 · grounded in chunks]
      DG2[propose edges\nRefD prereq signal + LLM + cosine]
      DG3[gpt-4o verify high-impact edges\ninduced_confidence · downgrade unsupported]
      DG4[persist concepts · edges · keypoints · quiz · chunks\nsource=digested · slice cache]
      DG1 --> DG2 --> DG3 --> DG4
    end
    G --> FS1
    FS4 --> DG1
    DG4 --> CG[(Concept graph · SQLite\nconcepts · edges · keypoints · quiz · chunks\nprereq solid · similarity dashed · digested)]

    %% ===================== INNER LOOP — LangGraph, checkpointed =====================
    CG --> GE[goal_elicit\ngoal_type → Bloom ceiling]
    GE --> PL[planner\nroute over target concepts]
    PL -->|new concept| IND[induce_scaffold\nderive prereqs · mine misconceptions]
    PL -->|multi-stop route| OT[orient_tour\nshow the roadmap first]
    IND --> SN
    OT --> SN
    PL -->|else| SN
    SN{select_next\n↻ next concept · or done}
    SN -->|next concept| RT[retrieve evidence\ncited chunks]
    RT -->|concept has keypoints| IK[init_kp → teach_kp\npaper-grounded explanation]
    RT -->|no keypoints| LT[teach · legacy fallback]

    subgraph TA [TEACH · ASSESS — keypoint by keypoint]
      direction TB
      IK --> AN[assess_next\nquiz at rising Bloom · learner answers]
      AN -->|lost| HL[handle_lost\nre-explain · no grade]
      HL --> AN
      AN -->|answer| GK[grade_kp\nBKT/Rasch mastery · detect misconception\nfrontier escalation near threshold]
      GK -->|correct → Bloom up · or hold| AN
      GK -->|wrong · retries left| RK[reteach_kp\nswitch strategy]
      RK --> AN
      GK -->|mastered ≥ threshold · or reteach exhausted| AK[advance_kp]
    end
    AK --> SN

    subgraph LEG [fallback — concepts without authored keypoints]
      direction TB
      LT -->|has quiz| CK[check · Socratic Q]
      LT -->|quizless| LEC[lecture · no mastery claim]
      CK --> GR[grade · BKT · detect misconception]
      GR -->|misconception · retries left| RE[reteach] --> LT
      GR -->|missing prereq| DI[diagnose → replan\ninsert missing prereq]
    end
    GR -->|mastered| SN
    LEC --> SN
    DI --> SN

    %% ===================== ARTIFACTS + NEXT =====================
    SN -->|all concepts done| ART
    ART[make-artifact · ARTIFACT · OW-5\nselect format → mind-map · notes · slides ·\nworked-example · combination\nretrieval prompt + resolving citations]
    ART --> RN[recommend-next · OW-6\nhard-prereq filter + mastery-gain ranker]
    RN --> DONE([✅ session done])
    CG -.on demand · deck · notes · map.-> ART

    %% ===================== COST SPINE — single metered chokepoint =====================
    subgraph SPINE [Cost spine · OW-0]
      RTR[router\ntier registry · per-session budget cap + 80% alert\nresult cache · strict liveness · cost_ledger]
    end
    FS1 -.meter.-> RTR
    DG1 -.-> RTR
    DG3 -.-> RTR
    GE -.-> RTR
    GK -.-> RTR
    ART -.-> RTR

    classDef disc fill:#dde6f2,stroke:#3f4b5e,color:#0f1b2b;
    classDef dig fill:#c7ecd4,stroke:#258a51,color:#0c3019;
    classDef teach fill:#d7ccff,stroke:#5b49c4,color:#1c1444;
    classDef spine fill:#ffdf9e,stroke:#b3700d,color:#43280a;
    classDef art fill:#ffd9ec,stroke:#b03a7a,color:#3d0f27;
    classDef store fill:#eaf3ff,stroke:#2d5d8f,color:#0f1b2b;
    classDef pending fill:#eee,stroke:#999,color:#555,stroke-dasharray:4 3;
    class G disc;
    class FS1,FS2,FS3,FS4 disc;
    class DG1,DG2,DG3,DG4 dig; class CG store;
    class GE,PL,IND,OT,SN,RT,IK,AN,HL,GK,RK,AK,LT,CK,LEC,GR,RE,DI teach;
    class ART art; class RN pending; class DONE store; class RTR spine;
```

> **Reading it:** DISCOVER + DIGEST are the open-world additions that *construct* the graph; everything
> from `goal_elicit` down is the checkpointed LangGraph inner loop (concepts **with** authored keypoints
> take the `teach_kp → assess_next → grade_kp → reteach_kp` path; concepts **without** take the legacy
> `teach → check → grade → diagnose/replan` fallback). Mastery is always BKT/Rasch from real answers,
> never LLM self-judgement.

**Stage skills** the outer loop invokes (each contracted, metered, live-verified):

| Stage | Status | What it does |
|:--|:--:|:--|
| **find-sources** (DISCOVER) | ✅ live | goal + intent → real OpenAlex/Wikipedia sources, ranked by relevance × authority, top-k full text fetched |
| **digest-corpus** (DIGEST) | ✅ live | sources → distinct concepts → prerequisite (RefD **+** LLM) and similarity edges → `gpt-4o` verify → grounded, cited graph |
| **teach / assess** (inner loop) | ✅ live | per-keypoint adaptive teaching; goal-elicited Bloom ceiling; metered grade with frontier escalation near the mastery threshold; MCQ distractors + flaw gate + IRT difficulty; FSRS spacing + retention probe; mastery from answers (BKT/Rasch), never LLM self-judgment |
| **make-artifact** (ARTIFACT) | ✅ live | scenario → format selector → mind-map / Cornell notes / Marp slides / worked-example / combination; every artifact carries a retrieval prompt + resolving citations |
| **recommend-next** | ⏳ OW-6 | hard-prereq filter + soft mastery-gain ranker |

---

## Live-first — the validation principle

Open-world capability is meaningless if only tested offline. So **every capability skill has a LIVE gate** that runs against a real provider and asserts structure + quality + **real metered cost**; offline gates are kept only for deterministic safety/math. A strict mode makes a real call *provably distinct* from a silent fallback (a dead provider raises, never quietly returns a fixture).

What this caught and fixed, on real runs:
- the digest's `frontier` tier was silently calling `gpt-4o-mini` (billed at gpt-4o rates) — **tier routing fixed**, the judge now runs on real `gpt-4o`;
- a chunk-id format bug dropped **100%** of proposed edges — fixed; edges now build;
- the cheap model self-judging gave false confidence — the real `gpt-4o` judge corrects it; and a non-LLM **RefD** signal recovers genuine prerequisites the judge alone rejects.

A full digest (discover → 8 concepts → RefD+LLM edges → gpt-4o judge) costs **≈ $0.003**. Offline, everything runs at **$0**.

---

## Quick start

```bash
pip install -r requirements.txt

# Offline gates (deterministic, $0, no key, no network)
python -m litnav.evaluation.verify_cost      # cost spine: metering + budget cap + record-only refusal
python -m litnav.evaluation.verify_digest    # digest determinism/schema unit gate
python -m litnav.evaluation.verify_discover  # find-sources parsing/rank/dedup/intent
python -m litnav.evaluation.verify_teach_assess  # goal/Bloom/flaw-gate/FSRS/strategy determinism
python -m litnav.evaluation.verify_artifact  # format selector + mind-map/combination + citations
python -m litnav.evaluation.verify_m0        # legacy closed-world gates (still green)
pytest -q                                    # full suite — 268 passed

# LIVE gates (real provider; set LITNAV_LLM_PROVIDER=openai + LITNAV_LLM_API_KEY in .env)
python -m litnav.evaluation.verify_liveness      # a real call is distinguishable from a fallback
python -m litnav.evaluation.verify_cost_live     # budget cap fires on real spend
python -m litnav.evaluation.verify_digest_live   # real LLM extracts + builds + judges a graph
python -m litnav.evaluation.verify_discover_live # real OpenAlex/Wikipedia/arXiv discovery → digest
python -m litnav.evaluation.verify_teach_assess_live # real goal elicit + distractors + metered grade
python -m litnav.evaluation.verify_artifact_live # real notes/slides/worked-example, citations resolve, metered
```

> Offline is the deterministic floor; the LIVE gates are the proof the capability works. See
> [`docs/2026-06-20-live-gate-execution-contract.md`](docs/2026-06-20-live-gate-execution-contract.md) for how they run (provider, budget cap, liveness, outage policy).

### Interactive agent UI (closed-world tutor)
```bash
python -m litnav.ui.server     # http://127.0.0.1:8000/tutor — Chat + Glass-box views
```

---

## Roadmap (open-world milestones)

| Milestone | Status | Proof |
|:--|:--:|:--|
| **Phase 0** · LLM liveness precondition | ✅ done · live | `verify_liveness` |
| **OW-0** · Cost spine (registry · metered router · budget cap · result cache) | ✅ done · live | `verify_cost_live` |
| **OW-1** · Data model (concept-graph + learner + cache + ledger schema) | ✅ done | schema + repo tests |
| **OW-2** · digest-corpus (RefD+LLM edges, gpt-4o verify, cache) | ✅ done · live | `verify_digest_live` |
| **OW-3** · find-sources (OpenAlex+Wikipedia, BM25+rerank, full text) | ✅ done · live | `verify_discover_live` |
| **OW-4** · TEACH/ASSESS (goal elicitation, Bloom quiz, distractors, IRT, FSRS, retention probe, escalation) | ✅ done · live | `verify_teach_assess_live` |
| **OW-5** · make-artifact (selector → map/notes/slides/worked-example/combination; retrieval prompt + citations on each) | ✅ done · live | `verify_artifact_live` |
| **OW-6** · recommend-next + dual frontend (Glass-box on `cost_ledger`, teacher override) | ⏳ next | — |
| **OW-7** · live cold-start (streamed real-topic digest→teach) | ⏳ pending (digest path already live) | — |

Full per-module detail, live results, costs, and the deferred/flagged items: **[`docs/OPEN-WORLD-STATUS.md`](docs/OPEN-WORLD-STATUS.md)**.

---

## Design principles
- **Grounded, not bluffing.** Open-domain ≠ ungrounded — it *fetches and digests* a source, then teaches from cited evidence.
- **The learner model is BKT/Rasch, never LLM self-assessment.**
- **Cost is a first-class constraint** — one metered chokepoint, a tier cascade, caching, a per-session budget cap; only approved models are callable, any other is record-only until approved.
- **Prereq edges are a soft constraint** (RefD + LLM + similarity fallback), never a hard gate; confidence is rule-computed and surfaced, never hallucinated.
- **No silent deviations.** Code is kept on one line with the research and the full spec; anything deferred is flagged in the spec.

---

## Tech stack
`LangGraph` (inner loop) · ReAct outer loop · `SQLite` (concept graph · learner model · cost ledger · caches) · OpenAI `gpt-4o-mini` (cheap) + `gpt-4o` (frontier judge) + `text-embedding-3-small` — provider-agnostic, offline-capable · OpenAlex / Wikipedia / arXiv (live discovery) · RefD (Liang 2015) prerequisite signal · `pytest`

## Documentation
| Doc | Role |
|:--|:--|
| [`docs/2026-06-20-open-world-research-brief.md`](docs/2026-06-20-open-world-research-brief.md) | research questions + rationale |
| [`docs/2026-06-20-open-world-literature-review.md`](docs/2026-06-20-open-world-literature-review.md) | verified literature + evidence grades + risks |
| [`docs/2026-06-20-open-world-architecture-spec.md`](docs/2026-06-20-open-world-architecture-spec.md) | **full architecture spec (source of truth)** |
| [`docs/OPEN-WORLD-STATUS.md`](docs/OPEN-WORLD-STATUS.md) | **per-module status / done / live results** |
| `docs/superpowers/plans/` | per-milestone implementation plans |
| `docs/archive/` | per-cycle eval log, audits, re-audit; `closed-world/` = legacy M0–M4 docs |

---

## Acknowledgments
Built for the **ICCSE 2026 Agentic AI Competition** (NTU · Tsinghua · Shandong · Xinjiang · UBC · Alibaba). Compute supported by QoderWork and Alibaba Cloud "Cloud for Research." **License:** MIT — see [LICENSE](LICENSE).
