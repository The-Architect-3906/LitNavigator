# Scenario 1 — diffusion-models
- **goal** (English): I want to deeply master how diffusion models generate images, end to end.
- **intended depth**: mastery  ·  **prior**: ML practitioner (knows CNNs/transformers)  ·  **domain**: ML / generative models

## OW-3 DISCOVER  (8.6s)
- intent classified: `cutting-edge`  ·  5 sources  ·  2 with full text
  - [web auth=0.86] Palette: Image-to-Image Diffusion Models
  - [web auth=0.76] Diffusion models in medical imaging: A comprehensive survey
  - [web auth=0.67] Denoising diffusion probabilistic models for 3D medical image generation
  - [wikipedia auth=0.50] Diffusion model
  - [web auth=0.87] Image Super-Resolution Via Iterative Refinement

- digesting top-ranked source: _Palette: Image-to-Image Diffusion Models_ (auth=0.86)

## OW-2 DIGEST  (33.7s)
- source: _Palette: Image-to-Image Diffusion Models_ (1303 chars full text)
- **persisted**: 8 concepts · 8 keypoints · 8 quiz items
- edges: 7 (5 prereq survived) · edge_accuracy=1.0 · kp_evidence_resolves=True
  - `image_to_image_translation` — Image-to-Image Translation
  - `conditional_diffusion_models` — Conditional Diffusion Models
  - `denoising_diffusion_objective` — Denoising Diffusion Objective
  - `loss_function_impact` — Impact of Loss Functions
  - `self_attention_importance` — Importance of Self-Attention
  - `unified_evaluation_protocol` — Unified Evaluation Protocol
  - `multi_task_diffusion_model` — Multi-Task Diffusion Model
  - `performance_comparison` — Performance Comparison

## OW-4 TEACH / ASSESS  (1.0s)
- goal_elicit → `mastery`  (intended `mastery` → match=True)
- strategy policy (expertise=expert) → `concise`
- seed quiz: _What is image-to-image translation?_
- distractors (live): 3 · flaw_gate=True (clean)
- grade (answer=key): score=1.0 mastery→0.55

## OW-5 ARTIFACT `notes`  len=1741 citations=['c0'] resolve=True
```markdown
# Study notes

## Image-to-Image Translation Tasks

**Cues:**
- What are the four tasks evaluated?
- How does the framework perform on these tasks?

**Summary:** Evaluates colorization, inpainting, uncropping, and JPEG restoration.

> Recall prompt: without looking, answer each cue above from memory.

## Conditional Diffusion Models

**Cues:**
- What is the role of conditional diffusion models?
- Do they require task-specific tuning?

```
## OW-5 ARTIFACT `mindmap`  len=607 citations=['c0'] resolve=True

## COST  tokens=11372 usd=0.01563 was_live=True