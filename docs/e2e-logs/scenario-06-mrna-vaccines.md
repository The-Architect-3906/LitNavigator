# Scenario 6 — mrna-vaccines
- **goal** (English): I need a working understanding of how mRNA vaccines are designed.
- **intended depth**: functional  ·  **prior**: interested layperson  ·  **domain**: Biochemistry

## OW-3 DISCOVER  (5.7s)
- intent classified: `systematic`  ·  6 sources  ·  1 with full text
  - [web auth=0.86] mRNA vaccines for infectious diseases: principles, delivery and clinical translation
  - [web auth=0.72] Innate immune mechanisms of mRNA vaccines
  - [web auth=0.63] mRNA vaccines in disease prevention and treatment
  - [web auth=0.62] The Storage and In-Use Stability of mRNA Vaccines and Therapeutics: Not A Cold Case
  - [web auth=0.65] Next‐Generation Vaccines: Nanoparticle‐Mediated DNA and mRNA Delivery
  - [web auth=0.60] mRNA vaccines for cancer immunotherapy

- digesting top-ranked source: _mRNA vaccines in disease prevention and treatment_ (auth=0.63)

## OW-2 DIGEST  (38.3s)
- source: _mRNA vaccines in disease prevention and treatment_ (1523 chars full text)
- **persisted**: 7 concepts · 7 keypoints · 7 quiz items
- edges: 7 (3 prereq survived) · edge_accuracy=0.75 · kp_evidence_resolves=True
  - `mrna_vaccine_design` — mRNA Vaccine Design
  - `mrna_synthesis` — mRNA Synthesis
  - `vaccine_delivery` — Vaccine Delivery Mechanisms
  - `adjuvant_technologies` — Adjuvant Technologies
  - `disease_application` — Disease Applications of mRNA Vaccines
  - `challenges_in_design` — Challenges in mRNA Vaccine Design
  - `future_prospects` — Future Prospects of mRNA Vaccines

## OW-4 TEACH / ASSESS  (1.3s)
- goal_elicit → `functional`  (intended `functional` → match=True)
- strategy policy (expertise=intermediate) → `worked_example`
- seed quiz: _What is the primary purpose of mRNA vaccine design?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1212 citations=['c0'] resolve=True
```markdown
# Study notes

## mRNA Vaccine Design

**Cues:**
- How are mRNA vaccines designed to trigger immune responses?
- What diseases can mRNA vaccines target?

**Summary:** mRNA vaccines are tailored to provoke specific immune responses.

> Recall prompt: without looking, answer each cue above from memory.

## mRNA Synthesis

**Cues:**
- What techniques are used to synthesize mRNA for vaccines?
- How does mRNA synthesis contribute to vaccine effectiveness?

```
## OW-5 ARTIFACT `mindmap`  len=496 citations=['c0'] resolve=True

## COST  tokens=10598 usd=0.014231 was_live=True