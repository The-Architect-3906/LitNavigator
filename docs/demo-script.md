# Demo Script

This is the competition demo path. The demo should show the highest stable milestone reached, while keeping lower milestone recordings available as fallbacks.

## Running the demo (implemented M0-M3)

The recordable artifact is the thin web panel. The CLI runner populates the demo SQLite, then the panel renders it (left: teaching transcript + decisions; right: route + route_version, learner model with three-color concepts and mastery/confidence bars, cited evidence).

```bash
# M1 — adaptive reroute (RAG fixture): wrong prereq answer inserts a prerequisite, route_version -> 2
python -m litnav.app demo-m1 --answer wrong_prereq
python -m litnav.app demo-m1 --answer correct        # counterfactual: advances cleanly

# M2 — agent corpus: misconception -> reteach -> pass
python -m litnav.app demo-m2 --answer cot            # ReAct=CoT misconception, reteach to analogy, mastery 0.40 -> 0.80
python -m litnav.app demo-m2 --answer correct        # counterfactual: advance without reteach
python -m litnav.app demo-m2 --answer exhausted      # reteach exhausted -> honest concede

# M3 — literature-induced scaffolding (the novelty): off-skeleton concept
python -m litnav.app demo-m3                          # induces multi_agent → multi_agent_debate (conf 0.75) + a misconception, taught as contested

# Visual panel (renders the last demo session; M3 marks curated vs induced + confidence_basis)
python -m litnav.ui.server                            # then open http://127.0.0.1:8000/sessions/<id>
```

> Gates remain the source of truth for state: `verify_m0` / `verify_m1` / `verify_m2` / `verify_m3` all pass fully offline. The M2 tutor loop runs on the agent paper pack; the M1 reroute currently runs on the RAG fixture and will be re-themed onto the agent route when the full agent curriculum is assembled in M3.

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

- a missing prerequisite (M1, RAG fixture): `negative_sampling`,
- an off-skeleton concept (M2/M3 run on the agent corpus): `multi_agent_debate` (see Money Shot 3).

> Note: M1's reroute demo runs on the RAG fixture (route above); M2 (reteach) and M3 (induction) run on the agent paper pack. The canonical commands are in "Running the demo" above.

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

**Milestone:** M2 (agent corpus)

**Setup:**

The user is learning `react` (ReAct).

**Misconception:**

```text
react_is_just_cot
```

The user thinks ReAct is just chain-of-thought prompting.

**Expected system behavior:**

```text
teach using direct explanation
check detects misconception
reteach switches to analogy
parallel quiz item passes
mastery rises (0.40 -> ~0.80)
confidence rises but remains calibrated
```

**What the viewer should see:**

- first explanation strategy,
- detected misconception,
- second strategy,
- changed mastery/confidence,
- cited evidence.

## Money Shot 3: Literature-Induced Scaffolding

**Milestone:** M3 (agent corpus)

**User prompt:**

```text
I keep seeing multi-agent debate. Where does it fit, and what are the pitfalls?
```

**Expected system behavior:**

`multi_agent_debate` is outside the curated skeleton, so the graph routes
`planner -> induce_scaffold` over already-ingested chunks, then teaches it through the
normal `retrieve -> teach -> check -> grade` loop.

It writes:

```text
multi_agent -> multi_agent_debate
source = induced
confidence_basis = {n_chunks, max_strength, multi_paper}  ->  rule-computed confidence
example: 1 chunk + explicit_assertion + single paper  ->  0.75
```

It also mines a misconception:

```text
wrong_model: more agents / rounds always improves the answer
correct_model: gains are task-dependent; debate can amplify a shared error (contested)
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

## Optional money shot: intent-mode contrast (M4)

If M4 intent modes land, record one high-impact contrast on the **same** agents corpus:

- **Researcher mode** → a long, deep route (full prerequisite chain + methods + open problems), high mastery bar.
- **Journalist mode** → a short, high-level route (landmark ideas + consensus/controversy map + questions to ask), "can hold the conversation" bar.

Two completely different routes from one engine and one corpus — the visual proof that the curriculum is re-scoped to *purpose*, not authored once. Skip if M4 time is tight; otherwise it is a strong utility-dimension moment.

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
