# Open-World — Live Model-Evaluation & Action Log

Per the standing rule: every skill gets a **metered live smoke test**; record the real cost, judge
whether the current models are adequate, and log any model need / capability gap as an **action**.
Only `gpt-4o-mini` (cheap) and `gpt-4o` (frontier) + `text-embedding-3-small` (embed) are enabled;
anything else stays `record-only` until approved.

---

## 2026-06-20 — OW-2 `digest-corpus` live smoke

**Run:** one live `digest()` over `data/seed/digest_sources_fixture.json` (provider=openai).

**Real metered cost (cost_ledger):**
| stage | tier | model | tokens | usd |
|---|---|---|---|---|
| digest | cheap | gpt-4o-mini | 464 | $0.000186 |
| digest | embed | text-embedding-3-small | 8 | ~$0 |
| **total** | | | **472** | **$0.000186** |

→ a full digest ≈ **1/50 of a cent**. Live testing is cheap; no cost concern.

**Model adequacy:**
- `gpt-4o-mini` **extraction: ADEQUATE** — produced 3 correct, source-grounded concepts (ReAct,
  Use of Tools, Reflexion). No better model needed for extraction.
- `text-embedding-3-small`: fine, negligible cost.
- `gpt-4o` (frontier judge) + cheap strength-labeler: **NOT YET EVALUABLE live** — see gap below.

**Finding / gap (capability, not model quality):** live extraction generates its **own** concept
slugs, but `build_edges` still takes the edge *list* from the hand-authored `candidate`. On a real
live run the slugs don't match → **0 edges** → the judge/strength paths never fire. So OW-2 is
**offline-fixture-complete but not live-complete**: it can extract concepts live but **cannot build
the prereq/similarity graph live** (the graph is the core output).

**ACTIONS:**
- [ ] **A1 — Live edge generation.** Add a step where the LLM proposes prereq/similarity edges over
  its *own* extracted concepts (not a fixed candidate), so a real live digest produces a graph.
  Until then, "live digest" = concepts only. **Decision needed:** pull into an OW-2 follow-up, or
  scope to **OW-7** (live cold-start). *(raised 2026-06-20)*
- [ ] **A2 — Re-evaluate the `gpt-4o` judge + strength-labeler** once A1 lands and they actually fire
  on live edges; only then can we judge whether `frontier` is adequate or a better/cheaper judge is
  worth recording.
- **No new model recorded this round** — `gpt-4o-mini` is adequate for what runs today.

---

## 2026-06-20 — Phase 0 liveness precondition live test

**Run (LIVE, provider=openai, strict):** `python -m litnav.evaluation.verify_liveness`.

**Live usage result:** real `complete_text` returned `'Pong.'`; `was_live()`=True; tokens=18 (>0) → provably hit the API, not a fallback. A forced bad model (`this-model-does-not-exist-zzz`) in strict mode **raised `LivenessError`** instead of silently falling back. **A bug was caught by running live** (the gate's first call omitted the required `fallback` kwarg) — fixed in `fix(live)`; exactly the failure the offline path can't surface.

**Cost table:**
| stage | tier | model | tokens | usd |
|---|---|---|---|---|
| liveness | cheap | gpt-4o-mini | 18 | $0.000007 |
| **total** | | | **18** | **$0.000007** |
(The forced-error call raised before metering → no row, no cost.)

**Evaluation:** liveness mechanism correct + cheap; no optimization needed. **Action A0 added:** the budget cap is now strict-raise-proven but has STILL never fired on real accumulating spend → `verify_cost_live` (doctrine §3) must force a real over-budget sequence and assert `BudgetExceeded`. A1/A2 (live edge-gen + judge evaluation) remain — that's Phase 1, where real model-adequacy testing happens. No new model needed.

---

## 2026-06-20 — OW-0..2 live-complete (first real edge-gen + gpt-4o judge)

**Runs (LIVE, provider=openai, strict):** `verify_cost_live` + `verify_digest_live` (real digest of the seed fixture's chunks).

**Live result:** `was_live()`=True. `gpt-4o-mini` extracted 3 concepts (react/tools/reflexion) and **proposed** prereq edges (the OW-2 zero-edge bug is fixed). The **real `gpt-4o` judge** then ran (tier-routing bug fixed — frontier was silently calling gpt-4o-mini) and **rejected all proposed prerequisites**, downgrading them to similarity. `verify_cost_live`: budget cap **fired on real accumulating spend** (first time ever). Both gates ALL PASS.

**Cost table (one live digest):**
| stage | tier | model | tokens | usd | calls |
|---|---|---|---|---|---|
| digest | cheap | gpt-4o-mini | 1083 | $0.000433 | 3 |
| digest | embed | text-embedding-3-small | 8 | ~$0 | 1 |
| digest_verify | frontier | **gpt-4o** | 114 | $0.00057 | 2 |
| **total** | | | **1205** | **$0.001003** | |

**Model adequacy (the real evaluation):**
- `gpt-4o-mini` **extraction: adequate** (sensible concepts).
- `gpt-4o-mini` **EDGE PROPOSAL: INCONCLUSIVE — do NOT attribute to the model.** edge_accuracy 0.0 is heavily CONFOUNDED: the fixture is 3 one-sentence chunks, and a prerequisite cannot be established from one sentence, so the judge's "reject for insufficient evidence" is largely *correct behavior on thin input*, not proof the proposal was wrong. The metric also conflates proposal-quality with evidence-sufficiency, and n=2 runs is far too small to read run-to-run variance as "weak." **Proposal adequacy is not measurable until OW-3 supplies real full-text.** (Earlier draft over-claimed "not adequate" — retracted.)
- `gpt-4o` **judge: relatively clean signal — cheap self-judging rubber-stamps.** cheap-as-judge gave acc 1.0 on the same edges the frontier judge rejected (acc 0.0). Accepting unsupported claims is the documented LLM self-judge failure mode (re-audit Risk C), so "don't let the cheap model self-judge; use frontier for the verify pass" is supported — though even this wants richer evidence to be conclusive. Cost ~$0.00057/run.
- live `quiz_seeds`: empty (gpt-4o-mini returned nothing usable) — minor; quiz is OW-4.

**ACTIONS:**
- [ ] **A1 — edge-proposal adequacy is INCONCLUSIVE; do NOT record a model need yet.** The 0.0 is confounded by thin (3-sentence) evidence + appropriately-conservative judge + n=2. **Re-evaluate at OW-3 with real full-text:** give rich evidence, compare cheap-proposal vs frontier-proposal on the SAME evidence, judge with frontier + a human-annotated calibration sample. Only if cheap proposals are still largely rejected on rich evidence is it a model signal → then consider `RECORDED_NEEDS` (never enable without approval). Nothing recorded now.
- [ ] **A-quiz — live quiz-seed gen returns empty;** fix or fold into OW-4 ASSESS (quiz is OW-4's domain).
- [ ] **edge_accuracy hard floor → OW-3** (thin seed evidence cannot support hard prerequisites; the gate reports the number and asserts graceful degradation instead).
- [ ] **⑫ learner_goal slug↔ID reconciliation → OW-4** (goal elicitation).
- **No new model enabled this round** — but A1 is the first concrete model-need signal; recorded, awaiting OW-3 confirmation + your approval.
