<div align="center">

# 🧭 LitNavigator

### An AI tutor that reads the research papers and then teaches *you* — step by step, adapted to what you actually know.

![Status](https://img.shields.io/badge/status-M1%20complete-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Framework](https://img.shields.io/badge/agent-LangGraph-black)
![License](https://img.shields.io/badge/license-MIT-green)
![ICCSE 2026](https://img.shields.io/badge/ICCSE%202026-Agentic%20AI%20Competition-purple)

</div>

---

## The gap nobody fills

> *You have a pile of papers. You need to understand the field. Who explains it to you?*

| | Models you | Adaptive teach/test/reteach | Prereq sequencing | Misconception diagnosis | From living literature | Curriculum source |
|:--|:--:|:--:|:--:|:--:|:--:|:--|
| Elicit / SciSpace | ✗ | ✗ | ✗ | ✗ | ✓ | — |
| NotebookLM | ✗ | ✗ | ✗ | ✗ | ✓ | — |
| Khanmigo / LearnLM | ✓ | ✓ | ✓ | ✓ | ✗ | human-authored |
| **LitNavigator** | ✓ | ✓ | ✓ | ✓ | ✓ | **induced from papers** |

That last column is the empty square: an adaptive tutor whose syllabus, prerequisites, and misconceptions are all derived from the open research frontier.

---

## How it works

```mermaid
flowchart TD
    A([Your learning goal]) --> P[planner\ntopo-sort route from concept graph]
    P --> S{In curated graph?}
    S -->|new concept| I[induce_scaffold\nderive prereqs · mine misconceptions\nfrom papers — source='induced' + evidence]
    S -->|yes| R[retrieve evidence]
    I --> R
    R --> T[teach\npaper-grounded explanation]
    T --> C[check\nSocratic Q]
    C --> G[grade\nBKT mastery update · detect misconception]
    G --> RT{tutor_router}
    RT -->|mastered ≥ 0.8| ADV[advance]
    RT -->|misconception| RE[reteach\nswitch strategy]
    RE --> T
    RT -->|missing prereq| DG[diagnose + replan\ninsert prereq into route]
    RT -->|exhausted| CC[concede honestly]
    CC --> ADV
    DG --> S
    ADV --> S

    classDef base fill:#dde6f2,stroke:#3f4b5e,color:#0f1b2b;
    classDef teach fill:#d7ccff,stroke:#5b49c4,color:#1c1444;
    classDef route fill:#ffdf9e,stroke:#b3700d,color:#43280a;
    classDef induce fill:#c7ecd4,stroke:#258a51,color:#0c3019;
    classDef gap fill:#ffd0bf,stroke:#cf4f24,color:#481606;
    class A,P,S,R,ADV base;
    class T,C,G,RE teach;
    class RT route;
    class I induce;
    class DG,CC gap;
```

**Three loops in one system:**

| Loop | What it does |
|:--|:--|
| **Outer** `planner → advance / replan` | Decides what concept comes next; inserts a missing prereq the moment a quiz exposes the gap |
| **Inner** `teach → check → grade → reteach` | Teaches one concept; switches explanation strategy on a detected misconception; honestly concedes rather than looping forever |
| **Induction** `induce_scaffold` | When you step off the graph, induces prereqs and mines misconceptions from the corpus — confidence computed by a transparent evidence rule, never hallucinated |

---

## Three demo moments

```
① "Let me re-explain from a different angle."
   You've understood dense retrieval as keyword matching.
   → Mastery 0.40 → 0.82. Strategy switched. Route advances.

② "You need to shore this up first."
   Contrastive learning quiz reveals negative sampling is missing.
   → Prereq inserted mid-session. route_version increments.

③ "This concept isn't in your map yet — let me go to the papers."
   You ask about hard-negative mining (off-graph concept).
   → induce_scaffold reads corpus, derives prereq edge, mines one misconception,
     teaches it as "still-contested", every claim backed by chunk id.
```

---

## Quick start

```bash
pip install -r requirements.txt
python -m litnav.evaluation.verify_m0   # G0: state machine + SQLite writes
python -m litnav.evaluation.verify_m1   # G1: route replans on a prereq gap (LangGraph + checkpoint)
pytest -q                               # full test suite
```

Expected `verify_m0` output:
```
G0 PASS: session written
G0 PASS: route written
G0 PASS: learner_state updated
G0 PASS: quiz_attempt written
G0 PASS: decision written
G0 PASS: offline run
```

> M0 and M1 require no LLM key and no network access. The LLM (Qwen, with offline fallback) enters at M2.

---

## Roadmap

| Milestone | What it proves | Status |
|:--|:--|:--:|
| **M0** · Fake-data walking skeleton | State machine loop + SQLite persistence | ✅ Done |
| **M1** · Navigator | Route changes because of learner state; LangGraph StateGraph + prereq replan + SqliteSaver checkpoint (G1 green) | ✅ Done |
| **M2** · Tutor | teach → reteach → concede; misconception detection (Qwen / offline fallback) | ⬜ Next |
| **M3** · Literature induction | `induce_scaffold` — the core novelty; confidence rule-computed | ⬜ |
| **M4** · Polish | UI, hybrid retrieval, cross-session memory | ⬜ |

> Every milestone is a self-contained, demoable, submittable build — no matter where progress stops.
> M1's gate (G1) passes via the `verify_m1` transcript; the thin web panel is the remaining M1 UI item and is folded into the upcoming UI work.

---

## Design principles

- **Nothing is black-box.** Every routing decision leaves a rationale chain: answer → concept/misconception → action taken.
- **Confidence ≠ mastery.** After one question, mastery may look high but confidence is low — the system says so explicitly.
- **Induced scaffolding is never silent.** Induced prereqs and misconceptions are marked `source='induced'`, with evidence chunks and rule-computed confidence attached.
- **Honest concede.** If the system has tried multiple explanations and hasn't gotten through, it flags low confidence and moves on — it does not pretend to have taught.

---

## Tech stack

`LangGraph` · `SQLite + FTS5` · `Chroma` (M4) · `bge-m3` embeddings (M4) · Qwen (M2+, model-agnostic) · `pytest`

---

## Acknowledgments

Built for the **ICCSE 2026 Agentic AI Competition** (NTU · Tsinghua · Shandong · Xinjiang · UBC · Alibaba).
Compute supported by QoderWork and Alibaba Cloud "Cloud for Research."

**License:** MIT — see [LICENSE](LICENSE).
