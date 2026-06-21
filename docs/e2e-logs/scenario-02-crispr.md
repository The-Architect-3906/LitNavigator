# Scenario 2 — crispr
- **goal** (Chinese): 给我一个关于 CRISPR 基因编辑原理的快速概览。
- **intended depth**: survey  ·  **prior**: undergraduate biology background  ·  **domain**: Biology / gene editing

## OW-3 DISCOVER  (7.2s)
- intent classified: `crash-course`  ·  6 sources  ·  3 with full text
  - [web auth=0.71] Mechanism and Applications of CRISPR/Cas-9-Mediated Genome Editing
  - [web auth=0.86] CRISPR/Cas Genome Editing and Precision Plant Breeding in Agriculture
  - [web auth=0.61] Spatiotemporal control of CRISPR/Cas9 gene editing
  - [web auth=0.63] Principles, Applications, and Biosafety of Plant Genome Editing Using CRISPR-Cas9
  - [web auth=0.71] Genome-Editing Technologies: Principles and Applications
  - [web auth=0.62] Precision genome editing in the CRISPR era

- digesting top-ranked source: _Mechanism and Applications of CRISPR/Cas-9-Mediated Genome Editing_ (auth=0.71)

## OW-2 DIGEST  (35.9s)
- source: _Mechanism and Applications of CRISPR/Cas-9-Mediated Genome Editing_ (1764 chars full text)
- **persisted**: 7 concepts · 7 keypoints · 7 quiz items
- edges: 7 (4 prereq survived) · edge_accuracy=1.0 · kp_evidence_resolves=True
  - `crispr_cas9_system` — CRISPR/Cas-9 System
  - `guide_rna_function` — Function of Guide RNA (gRNA)
  - `cas9_nuclease_mechanism` — Mechanism of Cas-9 Nuclease
  - `genome_editing_steps` — Steps of Genome Editing
  - `repair_mechanisms` — DNA Repair Mechanisms
  - `applications_of_crispr` — Applications of CRISPR/Cas-9
  - `challenges_in_crispr` — Challenges in CRISPR Technology

## OW-4 TEACH / ASSESS  (0.8s)
- goal_elicit → `survey`  (intended `survey` → match=True)
- strategy policy (expertise=novice) → `overview`
- seed quiz: _What is the primary function of the CRISPR/Cas-9 system?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1443 citations=['c0'] resolve=True
```markdown
# Study notes

## CRISPR/Cas-9 System Overview

**Cues:**
- What are the main components of the CRISPR/Cas-9 system?
- What are the applications of CRISPR/Cas-9?

**Summary:** Key genome editing tool with diverse applications.

> Recall prompt: without looking, answer each cue above from memory.

## Function of Guide RNA (gRNA)

**Cues:**
- How does gRNA recognize target DNA sequences?
- What role does gRNA play in genome editing?

```
## OW-5 ARTIFACT `mindmap`  len=481 citations=['c0'] resolve=True

## COST  tokens=12406 usd=0.017488 was_live=True