# Open-World LitNavigator — Live-First Re-Audit (Decision-Grade)

**Date:** 2026-06-20 · **Method:** 6 parallel artifact auditors → adversarial critic → opus synthesis (8 agents, ~494k tokens), all under a **live-first lens** (offline-fixture gates validate plumbing, not the open-world capability).

**Bottom line:** ~**60% survives** (orchestration spine, metering plumbing, pure safety/math, `extract.py`'s real live call, research content); ~**40% must be redone or re-grounded** (the edge stage, the judge semantics, the validation doctrine, the milestone order). **OW-0 is downgraded from "survives" to "reframe"** because of a live budget-cap hole. The single deepest finding (below) was missed by every first-pass auditor and caught only by the adversarial pass.

---

## Per-artifact verdicts

| Artifact | Verdict | One-line why |
|---|---|---|
| `litnav/llm/client.py` | **REDO (semantics)** | `except Exception: return fallback` + `_tls.cost=0` on every call → live failure and live success are observationally identical at gate + ledger. Root enabler; nobody opened it first pass. |
| `litnav/digest/edges.py` (edge stage) | **REDO** | LLM never *proposes* edges; loops a hand-authored `candidate["prereq_edges"]` and filters `if prereq_slug not in slugs`. Live slugs ≠ candidate slugs → 100% dropped → zero edges. |
| `litnav/digest/verify.py` (judge) | **REDO (semantics)** | `judge_labels.get(key, True)` — unknown live key defaults to "genuine prerequisite" (rubber stamp). `[:sample_n]` is order-biased, pre-downgrade, self-referential. |
| `litnav/digest/pipeline.py` | **REFRAME** | Cache hit returns empty `DigestResult`; `quiz_seeds` replayed from candidate. Spine itself sound. |
| `litnav/digest/contract.py::slice_key` | **REFRAME** | Content-insensitive key → two live runs with different slugs collide; run 2 gets `cache_hit`+empty, run 1's edgeless graph becomes permanent truth. |
| `litnav/digest/extract.py` | **SURVIVES (caveat)** | Genuinely calls the LLM, accepts its concepts — the proof the architecture *can* go live. Caveat: its "live proof" needs the liveness fix to be trustworthy in general. |
| `litnav/evaluation/verify_digest.py` | **REDO (as capability gate)** | Runs only `provider=none`; candidate replays into itself. Keep ONLY as a formula/schema unit test. |
| OW-0 cost spine | **REFRAME (not "survives")** | Math/state-machine correct, BUT budget cap is structurally unreachable on a degraded live session: failures meter $0 → `session_spend` never accumulates → `BudgetExceeded` never fires. |
| OW-1 storage | **REFRAME** | DDL/writers correct for plumbing, but no `slice_key` on concepts/edges, no `paper_chunks` rows for digested text (dangling evidence FKs), `learner_goal` stores int IDs set pre-digest, `digest_cache` has no model key. Cache is a "skip" flag, not a re-readable slice. |
| research brief | **REFRAME (2 pts)** | Strong on capability; warm/cold framing (§7/§8 "live-digest is the highlight, not the default") inverts live-first. |
| literature review | **REFRAME** | Risks A/B correct; misses C (edge-accuracy judge has no ground-truth calibration), D (open-web hallucination uncharacterized — OpenScholar/STORM are academic-corpus numbers), E soft-pedalled; closed-corpus grades unlabeled. |
| architecture spec | **REFRAME (doctrinal)** | Design sound; §6/§10/§9 validation doctrine is backwards (offline golden gate as capability proof; live deferred to OW-7). |
| OW-2 plan + seed fixtures | **REFRAME / QUARANTINE** | Bakes "offline=replay candidate, golden gate=THE gate"; fixture slugs known to diverge from live → the green gate actively misleads. |

---

## Systemic findings

### Finding 1 (META, deepest — missed by every first-pass auditor, caught by the adversarial pass): the silent-fallback client makes every live gate hollow.
`litnav/llm/client.py` wraps every LLM and embed call in `except Exception: return fallback` and sets `_tls.cost = 0` at entry. Consequences (verified in code):
- **Live success and silent degradation are observationally identical** at gate and ledger. A dead provider (429, timeout, auth, content-filter, malformed JSON) returns the candidate fixture, records a $0 ledger row, raises nothing, logs nothing.
- **The budget cap is structurally unreachable on a degraded session**: `_meter` reads `last_token_cost()` = `_tls.cost`, which stays 0 on the except branch → spend never accumulates → `BudgetExceeded` can never fire on a failing/retrying live session.
- **Therefore every "live gate" is satisfiable by a broken provider** unless it FIRST asserts liveness. The prerequisite to all live validation is a **liveness assertion**: a call returns provably-live output (`tokens > 0`, output structurally distinct from the fallback) or it raises — never silently substitutes the fixture inside a gate.

> Honest nuance (correcting a slight adversarial overreach): for the specific OW-2 live smoke, the differing slugs (`react`/`tools_use`/`reflexion` vs candidate `tool_use`/`reason_act`/`self_reflection`) *did* prove the LLM ran. But the structural risk and the budget-cap hole are real regardless, and you cannot rely on "output happened to differ" as a liveness proof in a gate.

### Finding 2 (named defect): the validation doctrine treats the offline golden gate as capability proof.
Spec §6 (every skill "must run offline-deterministically when `provider=none`"), §10 ("live smoke … never in the offline gate"), and the OW-2 plan ("offline = replay a prepared candidate … gated offline against a golden graph"). The OW-2 zero-edge incident is the proof: offline, `complete_json` returns the candidate, so the candidate replays into itself and the slug-join is never exercised against an independently-generated concept set.

### Finding 3 (milestone-ordering defect): live is deferred to the LAST milestone.
§9 builds everything offline and bolts the genuinely live end-to-end path on at OW-7. Live discovery → digest → teach is the spine and must be exercised on real input from the FIRST capability milestone, so slug-mismatch / zero-edge / cost-overrun / silent-fallback failures surface in week one, not after six green-but-hollow gates.

### Finding 4 (under-priced live cost/latency/non-determinism, confirmed in code):
- Budget cap unreachable on degraded sessions (Finding 1).
- **Double frontier-judge cost**: `pipeline.py` calls `_judge` via both `edge_accuracy` and `verify_edges` on the same high-impact edges → 2× gpt-4o per high-impact edge live (the "1/50 of a cent" was a zero-edge run where the judge never fired).
- Order-biased quality metric (`verify.py` `[:sample_n]` first-10, no shuffle, pre-downgrade, same model family).
- Silent embed disablement (`edges.py` `centroid={}` on embed failure → accept-all similarity, $0 embed row).
- Cache poisoning by non-determinism (content-insensitive `slice_key` + empty cache-hit).
- **No CI execution contract** for making a non-deterministic, network-bound, cost-incurring, silently-degrading live call a BLOCKING gate (budget, timeout/retry, outage=skip-loud, key handling).

### What genuinely survives — do NOT redo
`extract.py` (real live call); `induced_confidence` + downgrade-rule branching + USD formula + record-only refusal + thread-local cost isolation + `slice_key` determinism + cache memoization (legit offline safety/math); the **metering chokepoint topology** (every call routes through `router`); the orchestration spine; research/lit-review capability content; the "every slice is cold, no warm allowlist" cache posture.

---

## Proposed live-first doctrine (replaces spec §6 contract language + §10)

**§0 Prime directive — liveness before any live assertion (NEW):** add `LITNAV_LLM_STRICT` mode to `client.py` where `complete_json`/`complete_text`/`embed_texts` **raise** on provider error instead of returning the fallback; silent fallback survives ONLY for `provider=none` runtime degraded mode, never inside a gate. Add `was_live()` = parsed real response AND `tokens>0` AND output structurally distinct from the supplied fallback. Every live gate asserts `was_live()` first.

**§1 What stays OFFLINE (safety/math ONLY):** `induced_confidence` + pure formulas; the downgrade-rule branching; `slice_key`/schema/CHECK/PK-collision/migrations; the budget-cap state machine + record-only refusal (with a live confirm per §3); FSRS due-at; cache memoization. **A green offline run is never evidence a capability works.**

**§2 What MUST be validated LIVE (every capability skill):** `find-sources`, `digest-corpus`, `make-artifact`, teach/assess judging each get a REQUIRED live gate (`provider=openai`, strict) asserting **(A) structural invariants** (e.g. digest: every concept ≥1 evidence chunk id; **every edge endpoint is a slug actually extracted this run**; edge count > 0 when ≥2 related concepts; evidence ids resolve to non-empty text; recomputed confidence matches stored; downgraded edges ∈ `unverified_edges`), **(B) a quality threshold** (LLM-judge agreement on a SHUFFLED post-downgrade sample, asserted ≥ floor, with a human-annotated calibration note — never an exact value), **(C) real metered cost** (`cost_ledger` spend > 0 AND ≤ budget).

**§3 Cost-spine live confirm:** add `verify_cost_live` (real provider, strict, on-disk DB): assert `tokens>0`, `usd>0`, and that `BudgetExceeded` fires on a real over-budget sequence. Keep monkeypatched `verify_cost` as the offline math gate only.

**§4 CI execution contract (NEW):** API key handling; per-run USD cap on the gate; timeout + bounded retry (today: hard-coded 30s, zero retries); outage = skip-with-loud-warning (never silent pass, never flake-fail); tiny fixed real source slice per gate; de-dup the frontier `_judge` before any live gate runs.

**§5 Fixture posture:** `provider=none` returns a fixture as a RUNTIME degraded mode only; demote the golden-graph gate to a labeled "determinism/schema unit test — NOT capability evidence"; quarantine the seed golden graph.

---

## Milestone reordering (live to the front)

| Milestone | Change | Why |
|---|---|---|
| **client.py liveness (NEW, before all)** | strict mode raises on provider error + `was_live()` | prerequisite for every live gate; without it the budget cap is unreachable and gates pass on a dead provider |
| **OW-0 cost spine** | add `verify_cost_live` (tokens>0, usd>0, cap fires on real spend) | the cap has never fired on real spend |
| **NEW OW-2a — thin live cold-start spine (move to FRONT)** | real goal → live find-sources(tiny) → live digest(one slice) → teach one keypoint, behind the live gate | the only way slug-mismatch/zero-edge/$0-degradation surface immediately, not at OW-7 |
| **OW-2 digest** | REDO edge stage: LLM PROPOSES edges over live-extracted slugs (mirror `induce._extract_misconception`); candidate edges become offline fallback only; generate `quiz_seeds` live; replace golden gate with the live gate | the single missing capability that caused zero edges |
| **OW-3 find-sources** | promote "offline fixtures + one smoke" → required live gate | discovery exists only live |
| **OW-4 teach/assess** | live gate (uncertainty escalation fires, calibrated scores); shuffle + post-downgrade the edge_accuracy sample; de-dup double frontier `_judge` | judging IS a capability |
| **OW-5 make-artifact** | render from a LIVE-built graph; assert citations resolve to real live chunk ids | artifact can render from a fixture while citing nonexistent live chunks |
| **OW-7** | demote to "harden/scale live cold-start + de-dup + demo cache pre-fill" | live was the spine since OW-2a |

---

## Immediate execution plan

**Phase 0 — Liveness precondition (BLOCKS everything):** `LITNAV_LLM_STRICT` raise-on-error + `was_live()`; define the CI live-gate contract (key, per-run USD cap, timeout/retry, outage=skip-loud, tiny real slice).

**Phase 1 — Live edge-gen:** REDO `edges.py` with an LLM edge-PROPOSAL step over extracted slugs (candidate = offline fallback only); fix `verify._judge` so an unknown live key does NOT default True; generate `quiz_seeds` live; drop edges whose endpoints/evidence ids aren't real.

**Phase 2 — Live eval harness:** `verify_digest_live` (strict) asserting liveness + structure + quality-threshold + cost ≤ budget + cap-fires; demote `verify_digest` golden match to a labeled offline unit test; quarantine the golden fixture; add `verify_cost_live`.

**Phase 3 — Live-first ordering:** stand up OW-2a thin live cold-start spine; every later milestone DEEPENS it against its own live harness; OW-7 → hardening.

**Single most important change:** the liveness assertion in `client.py`. Without it, moving live to the front accomplishes nothing — every live gate stays satisfiable by a dead provider.
