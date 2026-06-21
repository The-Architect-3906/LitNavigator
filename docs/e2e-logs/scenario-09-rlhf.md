# Scenario 9 — rlhf
- **goal** (English): How do I apply reinforcement learning from human feedback to fine-tune an LLM?
- **intended depth**: functional  ·  **prior**: ML engineer who has fine-tuned models  ·  **domain**: ML / alignment

## OW-3 DISCOVER  (6.7s)
- intent classified: `applied`  ·  4 sources  ·  3 with full text
  - [wikipedia auth=0.50] Reinforcement learning from human feedback
  - [web auth=0.74] DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement learning
  - [web auth=0.66] Reflexion: Language Agents with Verbal Reinforcement Learning
  - [web auth=0.50] RLAIF vs. RLHF: Scaling Reinforcement Learning from Human Feedback with AI Feedback

- digesting top-ranked source: _Reinforcement learning from human feedback_ (auth=0.50)

## OW-2 DIGEST  (28.4s)
- source: _Reinforcement learning from human feedback_ (278 chars full text)
- **persisted**: 5 concepts · 5 keypoints · 5 quiz items
- edges: 6 (4 prereq survived) · edge_accuracy=1.0 · kp_evidence_resolves=True
  - `rlhf` — Reinforcement Learning from Human Feedback
  - `reward_model` — Reward Model
  - `human_preferences` — Human Preferences
  - `training_process` — Training Process
  - `alignment` — Alignment of Intelligent Agents

## OW-4 TEACH / ASSESS  (3.3s)
- goal_elicit → `functional`  (intended `functional` → match=True)
- strategy policy (expertise=intermediate) → `worked_example`
- seed quiz: _What does RLHF stand for?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1054 citations=['c0'] resolve=True
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
- What is the role of the reward model in RLHF?
- How is the reward model trained?

```
## OW-5 ARTIFACT `mindmap`  len=486 citations=['c0'] resolve=True

## COST  tokens=8503 usd=0.008516 was_live=True