# Demo Script

This is the competition demo path. The demo should show the highest stable milestone reached, while keeping lower milestone recordings available as fallbacks.

## Demo Topic

Use one stable topic:

```text
I want to understand retrieval-augmented generation (RAG) for scientific QA.
```

Initial route:

```text
Dense retrieval -> Contrastive learning -> RAG pipeline -> Evaluation / hallucination
```

The route intentionally leaves room for:

- a missing prerequisite: `negative_sampling`,
- an off-skeleton concept: `hard_negative_mining`.

## Money Shot 1: Reroute on Missing Prerequisite

**Milestone:** M1

**Setup:**

The user is learning `contrastive_learning`.

**Action:**

The quiz exposes that the user does not understand `negative_sampling`.

**Expected system behavior:**

```text
route_version += 1
negative_sampling is inserted before contrastive_learning
decision rationale cites the failed quiz and the prerequisite edge
```

**What the viewer should see:**

- route before,
- wrong answer,
- route after,
- reason for insertion.

## Money Shot 2: Reteach on Misconception

**Milestone:** M2

**Setup:**

The user is learning `dense_retrieval`.

**Misconception:**

```text
dr_is_keyword_match
```

The user thinks dense retrieval is just keyword/BM25 matching.

**Expected system behavior:**

```text
teach using direct explanation
check detects misconception
reteach switches to analogy
parallel quiz item passes
mastery rises
confidence rises but remains calibrated
```

**What the viewer should see:**

- first explanation strategy,
- detected misconception,
- second strategy,
- changed mastery/confidence,
- cited evidence.

## Money Shot 3: Literature-Induced Scaffolding

**Milestone:** M3

**User prompt:**

```text
I keep seeing hard negative mining. Where does it fit, and what are the pitfalls?
```

**Expected system behavior:**

`hard_negative_mining` is outside the curated skeleton, so `induce_scaffold` runs over already-ingested chunks.

It writes:

```text
negative_sampling -> hard_negative_mining
source = induced
confidence_basis = {n_chunks, max_strength, multi_paper}  ->  rule-computed confidence
example: 1 chunk + explicit_assertion + single paper  ->  0.75
```

It also mines a misconception:

```text
wrong_model: more negatives is always better
correct_model: hard negatives matter more than raw quantity
```

**What the viewer should see:**

- induced edge,
- source evidence,
- confidence basis,
- curated vs induced visual distinction,
- frontier label such as contested/open if evidence supports it.

## Counterfactual Branch

For perceived intelligence, show at least one counterfactual:

- wrong answer leads to reteach or replan,
- correct answer advances directly.

This proves the route is conditional, not a scripted transcript.

## Fallback Recordings

If M3 is unstable:

- record M2 as the main demo,
- show M3 as evidence screenshots or a short non-live segment.

If M2 is unstable:

- record M1 as the main demo,
- explain M2 as in progress only if there is real trace evidence.

If M1 is unstable:

- record M0 only as an engineering proof, not as a strong competition demo.

## Demo UI Requirements

The recordable artifact is the **thin web panel** (FastAPI + Jinja, started at M1 and extended each milestone), not a CLI transcript. It must show:

- current route,
- route version,
- current concept,
- quiz/check result,
- mastery,
- confidence,
- decision rationale,
- evidence chunks,
- provenance: curated or induced.

Avoid fake intelligence theatrics. The system should be decisive, brief, and traceable.
