# Live-Gate Execution Contract

Live gates (`verify_liveness`, future `verify_digest_live`, `verify_cost_live`) make REAL,
non-deterministic, billed, network calls. They are NOT offline CI gates. Rules:

- **Provider/key:** run with `LITNAV_LLM_PROVIDER=openai` and the key from `.env` (never committed,
  never printed). `provider=none` => the gate SKIPS with a clear message.
- **Strict liveness:** every live gate sets `LITNAV_LLM_STRICT=1` and asserts `was_live()` (tokens>0,
  not a fallback) before any capability assertion — a broken/skipped provider can never look like a pass.
- **Budget:** each live gate runs on a tiny fixed real input and passes a `budget` so the per-run spend
  is hard-capped; the gate asserts `cost_ledger` spend > 0 AND <= budget.
- **Outage policy:** on a provider outage the gate SKIPS with a loud warning (exit 0 + explicit SKIP
  line) — it must never silently pass and never flake-fail a merge.
- **Cost surfaced:** every live gate prints the metered `cost_ledger` (tokens + USD) it incurred.
- **Frontier de-dup:** before a live gate that judges edges, the double `_judge` call must be
  de-duplicated (see digest pipeline NOTE) so high-impact edges are not billed twice.
