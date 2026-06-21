# Scenario 10 — graph-neural-nets
- **goal** (French): Donne-moi une introduction aux réseaux de neurones sur graphes.
- **intended depth**: survey  ·  **prior**: data scientist new to graphs  ·  **domain**: Graph machine learning

## OW-3 DISCOVER  (5.3s)
- intent classified: `crash-course`  ·  6 sources  ·  3 with full text
  - [web auth=0.40] PRESENCE D’UNE PRÉDISPOSITION : PREMIER ÉPISODE D’UNE SÉRIE DE HUIT ÉPISODES SUR LE CERVEA
  - [web auth=0.16] Réseaux et signal : des outils de traitement du signal pour l'analyse des réseaux
  - [web auth=0.21] Réseaux de neurones à relaxation entraînés par critère d'autoencodeur débruitant
  - [web auth=0.08] Détection de communautés dynamiques dans des réseaux temporels
  - [web auth=0.16] Affectation de canaux dans les réseaux de téléphonie mobile cellulaire
  - [web auth=0.08] Apprentissage des réseaux de neurones profonds et applications en traitement automatique d

- digesting top-ranked source: _PRESENCE D’UNE PRÉDISPOSITION : PREMIER ÉPISODE D’UNE SÉRIE DE HUIT ÉPISODES SUR_ (auth=0.40)

## OW-2 DIGEST  (36.8s)
- source: _PRESENCE D’UNE PRÉDISPOSITION : PREMIER ÉPISODE D’UNE SÉRIE DE HUIT ÉPISODES SUR_ (1783 chars full text)
- **persisted**: 8 concepts · 0 keypoints · 8 quiz items
- edges: 6 (0 prereq survived) · edge_accuracy=0.0 · kp_evidence_resolves=True
  - `genetic_epigenetic_predisposition` — Prédisposition génétique et épigénétique
  - `synaptic_pruning` — Élagage synaptique
  - `neuroplasticity` — Neuroplasticité
  - `neurogenesis` — Neurogenèse
  - `neural_network_dynamics` — Dynamique des réseaux de neurones
  - `environmental_impact` — Impact de l'environnement
  - `mental_states_emergence` — Émergence d'états mentaux complexes
  - `neural_activity_regulation` — Régulation de l'activité neuronale

## OW-4 TEACH / ASSESS  (1.3s)
- goal_elicit → `survey`  (intended `survey` → match=True)
- strategy policy (expertise=novice) → `overview`
- seed quiz: _What is genetic and epigenetic predisposition?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1813 citations=['c0'] resolve=True
```markdown
# Study notes

## Modèle PRESENCE

**Cues:**
- Quel est l'objectif du modèle PRESENCE?
- Comment le modèle PRESENCE est-il structuré?
- Quel est le lien entre le modèle PRESENCE et les neurosciences de l'éducation?

**Summary:** Intégration des connaissances sur le développement cérébral.

> Recall prompt: without looking, answer each cue above from memory.

## Prédisposition génétique et épigénétique

**Cues:**
- Comment les connexions neuronales sont-elles établies?
- Quel rôle joue l'expérience dans le maintien des connexions neuronales?
```
## OW-5 ARTIFACT `mindmap`  len=447 citations=['c0'] resolve=True

## COST  tokens=11578 usd=0.004011 was_live=True