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
