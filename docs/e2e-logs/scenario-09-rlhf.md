# Scenario 9 — rlhf
- **goal** (English): How do I apply reinforcement learning from human feedback to fine-tune an LLM?
- **intended depth**: functional  ·  **prior**: ML engineer who has fine-tuned models  ·  **domain**: ML / alignment

## OW-3 DISCOVER  (3.4s)
- intent classified: `applied`  ·  3 sources  ·  3 with full text
  - [wikipedia auth=0.50] Reinforcement learning from human feedback
  - [wikipedia auth=0.50] Reinforcement learning
  - [wikipedia auth=0.50] Large language model

- digesting top-ranked source: _Reinforcement learning from human feedback_ (auth=0.50)

## OW-2 DIGEST  (33.4s)
- source: _Reinforcement learning from human feedback_ (278 chars full text)
- **persisted**: 5 concepts · 5 keypoints · 5 quiz items
- edges: 6 (4 prereq survived) · edge_accuracy=1.0 · kp_evidence_resolves=True
  - `rlhf` — Reinforcement Learning from Human Feedback
  - `reward_model` — Reward Model
  - `human_preferences` — Human Preferences
  - `training_process` — Training Process
  - `alignment` — Alignment of Intelligent Agents

## OW-4 TEACH / ASSESS  (1.4s)
- goal_elicit → `functional`  (intended `functional` → match=True)
- strategy policy (expertise=intermediate) → `worked_example`
- seed quiz: _What does RLHF stand for?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1071 citations=['c0'] resolve=True
```markdown
# Study notes

## Reinforcement Learning from Human Feedback (RLHF)

**Cues:**
- What is RLHF?
- How does RLHF align agents with human preferences?

**Summary:** Technique for aligning agents with human values.

> Recall prompt: without looking, answer each cue above from memory.

## Reward Model

**Cues:**
- What is the purpose of a reward model?
- How is a reward model trained?

```
## OW-5 ARTIFACT `mindmap`  len=486 citations=['c0'] resolve=True

## COST  tokens=4982 usd=0.008394 was_live=True