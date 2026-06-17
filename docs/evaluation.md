# Evaluation

This document turns the acceptance criteria into executable checks. Every milestone should have a command that proves its gate.

## Evaluation Philosophy

The demo must withstand poking. A UI transcript is not enough; the system must leave inspectable state behind.

Each check should verify durable evidence:

- database rows,
- route versions,
- state changes,
- cited chunk ids,
- decision rationales,
- provenance flags,
- confidence basis.

## Gate Commands

| Gate | Command | Purpose |
|---|---|---|
| G0 | `python -m litnav.evaluation.verify_m0` | fake-data loop writes real state |
| G1 | `python -m litnav.evaluation.verify_m1` | route changes on prerequisite gap |
| G2 | `python -m litnav.evaluation.verify_m2` | tutor loop branches and reteaches |
| G3 | `python -m litnav.evaluation.verify_m3` | induction creates evidence-backed scaffolding |

G0-G3 are all implemented and pass fully offline (M0-M3 complete).

**All gates run fully offline.** M2/M3 use the LLM only when `LITNAV_LLM_PROVIDER=qwen`; with the default `none` they take the deterministic fixture path, so `verify_m2`/`verify_m3` pass with no network. The live LLM is exercised separately during recording (see "Live LLM induction check" below) to satisfy the spec's "at least one live induction" rule.

## T1-T11 Acceptance Matrix

| Test | Stage | Verification evidence |
|---|---|---|
| T1 state truly written | M1 | `learner_state`, `quiz_attempts`, and `decisions` rows change after one check |
| T2 true three paths | M1-M2 | same concept supports advance, reteach, and diagnose/replan paths |
| T2b concede termination | M2 | exhausted reteach creates a `concede` decision and exits |
| T3 reteach truly switches | M2 | `tried_strategies` contains two different strategies |
| T4 rationale traceable | M1-M2 | decision rationale references check result, concept edge, and chunk id |
| T5 in-session learning gain | M2 | `tutor_turns.post_check_score > pre_check_score` using parallel items |
| T5b confidence calibration | M2 | confidence rises with `n_observations`; one-observation state is marked low confidence |
| T6 induction with evidence | M3 | induced edge/misconception has cited chunk and `confidence_basis` |
| T7 induction demoable | M3 | off-skeleton concept produces at least one induced element (offline fixture passes the gate; at least one live `provider=qwen` induction is shown during recording) |
| T8 honest provenance | M3 | UI/trace distinguishes curated vs induced and shows confidence basis |
| T9 jump-step interception | M2 bonus | request to skip ahead produces prerequisite warning |
| T10 no hallucinated citations | M2 | every teach/reteach assertion references a real chunk id |
| T11 runs offline | M0 | gate command succeeds without live external API calls |

## M0 Verification Details

`verify_m0` should:

1. create a fresh local SQLite DB,
2. seed the tiny RAG fixture,
3. run one deterministic session,
4. assert rows exist in core tables,
5. assert learner mastery changed,
6. assert a decision was written,
7. print one G0 PASS line per assertion.

Expected output:

```text
G0 PASS: session written
G0 PASS: route written
G0 PASS: learner_state updated
G0 PASS: quiz_attempt written
G0 PASS: decision written
G0 PASS: offline run
```

## M1 Verification Details

`verify_m1` should run two branches against the same route:

- correct answer: concept advances,
- prerequisite failure: `replan` inserts missing prerequisite and increments `route_version`.

It should assert:

- `route_version` changed only in the prerequisite-failure branch,
- rationale includes the failed concept, missing prereq, and source edge,
- the route remains acyclic.

## M2 Verification Details

`verify_m2` should run:

- misconception branch,
- reteach branch,
- concede branch.

It should assert:

- `reteach_count` increases,
- `tried_strategies` changes,
- `concede` exits without another reteach,
- cited chunk ids exist,
- confidence is lower than mastery after one observation.

## M3 Verification Details

`verify_m3` drives the compiled graph with an off-skeleton concept request and asserts:

- the request flows through the graph: `planner -> induce_scaffold -> select_next -> retrieve -> teach -> check -> grade`,
- an induced concept edge and a misconception are written with `source='induced'`,
- at least one evidence chunk is attached, and `confidence` matches the `induced_confidence` rule,
- `confidence_basis` is logged in `induction_log` and is machine-readable,
- the induced concept is slotted into the route and labeled with its frontier status,
- the induced concept is then **taught** by the normal inner loop (a `tutor_turn` is recorded for it).

## Live LLM Induction Check

The automated gates run offline on fixtures. To exercise the live provider during recording:

```bash
LITNAV_LLM_PROVIDER=qwen python -m litnav.app demo-m3
```

**What the live path currently does:** the LLM labels the *evidence strength* of the induced edge/misconception over the ingested chunks (confidence stays rule-computed); the offline candidate provides the structure as fallback. Confirm the `provider=qwen` path ran and the cited evidence chain is shown. This is a recording step, not a blocking gate — if the live call fails it falls back to the offline candidate.

**Not yet implemented (future work):** fully autonomous live induction — the LLM proposing the prerequisite edge and misconception *itself* from the real chunks. Real PDF chunk extraction is **done** (`data/seed/agents_corpus.json`, via `python -m litnav.ingest.pdf_extract`); what remains is pointing `induce` at the real corpus chunks and adding the extraction prompt. Until then the spec's "perform at least one live induction" rule is only partially met (strength labeling, not autonomous extraction).

## Manual Demo Checks

Automated gates prove state. Manual demo checks prove judge-facing clarity:

- Can a viewer see why the route changed?
- Can a viewer see which answer caused the change?
- Can a viewer open or inspect the evidence?
- Can a viewer distinguish curated vs induced?
- Can a viewer see confidence as separate from mastery?

If the answer to any of these is no, the UI is not ready for recording even if backend gates pass.
