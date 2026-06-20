# OW-0 Cost Spine — Implementation Plan

> ✅ **COMPLETED 2026-06-20.** Tasks 1–5 done (commits `aff4774`, `76bfc57`, `3e32065`, `117e1cb`,
> `9182519`) + utcnow cleanup. Full suite **134 passed**; `verify_cost` + `verify_m0/m2/m3` all PASS.
> (Pre-existing `verify_m1` failure is unrelated — OW-0 touched only the 6 cost files; see chat.)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the metering chokepoint every open-world LLM call must pass through — a model
registry (only approved models enabled), a cost ledger, per-call USD metering, and a per-session
budget cap — without breaking offline determinism.

**Architecture:** A new `litnav/llm/router.py` wraps the existing `litnav/llm/client.py`. Callers
ask the router for a *tier* (`cheap`/`frontier`); the router resolves the tier against
`litnav/llm/registry.py` (refusing disabled/record-only models), calls the underlying client,
reads `client.last_token_cost()`, computes USD from a per-tier rate, writes a row to the new
`cost_ledger` table via `litnav/storage/cost_repo.py`, and enforces an optional per-session token
budget by raising `BudgetExceeded`. Offline (`provider=none`) every call costs 0 tokens, so offline
sessions record 0-cost rows and never hit the budget — determinism preserved.

**Tech Stack:** Python 3.12, sqlite3, pytest. Reuses `litnav/llm/client.py`,
`litnav/storage/schema.py` (`DDL` + `init_db`), patterns from `litnav/ui/cost.py`.

**Spec:** [open-world architecture §5](2026-06-20-open-world-architecture-spec.md) (model router &
cost governance) + §4.3 (`cost_ledger`).

---

## File structure (locked decisions)

- Create `litnav/llm/registry.py` — `MODEL_REGISTRY` (enabled tiers), `RECORDED_NEEDS`
  (record-only, disabled), `resolve_tier()`, `is_enabled()`. One responsibility: *what models may
  be called and at what rate.*
- Create `litnav/storage/cost_repo.py` — `record_cost()`, `session_spend()`. One responsibility:
  *persist and total spend.* (Kept out of the large `repo.py` for focus.)
- Create `litnav/llm/router.py` — `complete_text()`, `complete_json()`, `BudgetExceeded`. One
  responsibility: *the metered chokepoint* (resolve tier → call client → meter → ledger → budget).
- Modify `litnav/storage/schema.py` — add the `cost_ledger` table to `DDL`.
- Create `litnav/evaluation/verify_cost.py` — the OW-0 gate (metering + budget fire).
- Tests: `tests/test_model_registry.py`, `tests/test_cost_repo.py`, `tests/test_router.py`,
  `tests/test_budget.py`.

Note: `litnav/ui/cost.py` is left unchanged (existing tests depend on it); the open-world Glass-box
meter will read `cost_repo.session_spend()` when those panels are built (OW-6), not in OW-0.

---

## Task 1: Cost ledger table + repo

**Files:**
- Modify: `litnav/storage/schema.py` (append one table to the `DDL` string)
- Create: `litnav/storage/cost_repo.py`
- Test: `tests/test_cost_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cost_repo.py`:

```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_record_and_total_spend():
    conn = _conn()
    cost_repo.record_cost(conn, session_id="s1", stage="teach", tier="cheap",
                          model="gpt-4o-mini", total_tokens=1000, usd=0.0004, cache_hit=False)
    cost_repo.record_cost(conn, session_id="s1", stage="assess", tier="frontier",
                          model="gpt-4o", total_tokens=500, usd=0.0025, cache_hit=False)
    cost_repo.record_cost(conn, session_id="other", stage="teach", tier="cheap",
                          model="gpt-4o-mini", total_tokens=9999, usd=9.9, cache_hit=False)

    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 1500
    assert round(spend["usd"], 4) == 0.0029     # 0.0004 + 0.0025, only session s1


def test_session_spend_empty_is_zero():
    conn = _conn()
    assert cost_repo.session_spend(conn, "nobody") == {"tokens": 0, "usd": 0.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cost_repo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'litnav.storage.cost_repo'`.

- [ ] **Step 3: Add the `cost_ledger` table to the schema**

In `litnav/storage/schema.py`, inside the `DDL = """ ... """` string, append this table just before
the closing `"""` (next to the other `CREATE TABLE IF NOT EXISTS` blocks):

```sql
CREATE TABLE IF NOT EXISTS cost_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    ts TEXT,
    stage TEXT,
    tier TEXT,
    model TEXT,
    total_tokens INTEGER DEFAULT 0,
    usd REAL DEFAULT 0,
    cache_hit INTEGER DEFAULT 0
);
```

- [ ] **Step 4: Implement `cost_repo.py`**

Create `litnav/storage/cost_repo.py`:

```python
"""Cost ledger: persist and total per-session LLM spend (the open-world metering store)."""
from __future__ import annotations

import datetime as _dt
import sqlite3


def record_cost(conn: sqlite3.Connection, *, session_id: str | None, stage: str, tier: str,
                model: str, total_tokens: int, usd: float, cache_hit: bool = False) -> None:
    """Append one metered call to cost_ledger. ts is UTC ISO-8601."""
    conn.execute(
        "INSERT INTO cost_ledger (session_id, ts, stage, tier, model, total_tokens, usd, cache_hit) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (session_id, _dt.datetime.utcnow().isoformat(timespec="seconds"), stage, tier, model,
         int(total_tokens), float(usd), 1 if cache_hit else 0),
    )
    conn.commit()


def session_spend(conn: sqlite3.Connection, session_id: str) -> dict:
    """Total tokens and USD recorded for a session (0/0.0 when none)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(usd), 0.0) "
        "FROM cost_ledger WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return {"tokens": int(row[0] or 0), "usd": round(float(row[1] or 0.0), 6)}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cost_repo.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add litnav/storage/schema.py litnav/storage/cost_repo.py tests/test_cost_repo.py
git commit -m "feat(cost): cost_ledger table + cost_repo record/total"
```

---

## Task 2: Model registry (only approved models callable)

**Files:**
- Create: `litnav/llm/registry.py`
- Test: `tests/test_model_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_registry.py`:

```python
import pytest
from litnav.llm import registry


def test_enabled_tiers_resolve_to_model_and_rate():
    cheap = registry.resolve_tier("cheap")
    assert cheap["model"] == "gpt-4o-mini"
    assert cheap["usd_per_1k"] > 0
    frontier = registry.resolve_tier("frontier")
    assert frontier["model"] == "gpt-4o"
    assert frontier["usd_per_1k"] > cheap["usd_per_1k"]   # frontier costs more


def test_unknown_tier_raises():
    with pytest.raises(ValueError):
        registry.resolve_tier("made_up")


def test_record_only_models_exist_but_are_not_callable():
    # Recorded needs are visible for governance but never resolvable as a callable tier.
    assert registry.RECORDED_NEEDS, "recorded needs list should not be empty (it documents asks)"
    for need in registry.RECORDED_NEEDS:
        assert "name" in need and "why" in need
        with pytest.raises(ValueError):
            registry.resolve_tier(need["name"])   # cannot be called silently


def test_is_enabled():
    assert registry.is_enabled("cheap") is True
    assert registry.is_enabled("frontier") is True
    assert registry.is_enabled("made_up") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'litnav.llm.registry'`.

- [ ] **Step 3: Implement `registry.py`**

Create `litnav/llm/registry.py`:

```python
"""Model registry — the single source of truth for which models the router may call.

Only ENABLED tiers are callable. Any other model need (including non-OpenAI providers, a
fine-tuned tutor model, a reranker, etc.) lives in RECORDED_NEEDS as documentation ONLY and is
NEVER resolvable — it cannot be called until a human promotes it into MODEL_REGISTRY.
`usd_per_1k` is a single blended per-tier rate (input+output averaged), enough for metering and
budget; a precise input/output split is a later refinement (YAGNI here).
"""
from __future__ import annotations

# Enabled tiers. usd_per_1k = blended estimate per 1,000 total tokens.
MODEL_REGISTRY: dict[str, dict] = {
    "cheap":    {"model": "gpt-4o-mini", "usd_per_1k": 0.0004},
    "frontier": {"model": "gpt-4o",      "usd_per_1k": 0.0050},
}

# Record-only: documented needs, DISABLED. Promote into MODEL_REGISTRY only on explicit approval.
RECORDED_NEEDS: list[dict] = [
    {"name": "mid", "why": "stronger QG/grading than gpt-4o-mini if a measured need appears"},
    {"name": "reranker", "why": "retrieval re-ranker beyond BM25+SPECTER, if needed"},
    {"name": "tutor-dpo-small", "why": "DPO-tuned small tutor model (cost/quality), incl. non-OpenAI"},
]


def is_enabled(tier: str) -> bool:
    return tier in MODEL_REGISTRY


def resolve_tier(tier: str) -> dict:
    """Return {model, usd_per_1k} for an ENABLED tier, else raise ValueError."""
    if tier not in MODEL_REGISTRY:
        raise ValueError(
            f"tier {tier!r} is not an enabled model. Enabled: {sorted(MODEL_REGISTRY)}. "
            f"Record-only needs (require approval): {[n['name'] for n in RECORDED_NEEDS]}."
        )
    return MODEL_REGISTRY[tier]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_model_registry.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add litnav/llm/registry.py tests/test_model_registry.py
git commit -m "feat(cost): model registry; only approved tiers callable, others record-only"
```

---

## Task 3: Router — the metered chokepoint

**Files:**
- Create: `litnav/llm/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_router.py`:

```python
import sqlite3
import pytest
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router
from litnav.llm import client as llm_client


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_offline_returns_fallback_and_records_zero(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    out = router.complete_text("teach this", tier="cheap", stage="teach",
                               session_id="s1", conn=conn, fallback="FALLBACK")
    assert out == "FALLBACK"                       # offline determinism preserved
    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 0 and spend["usd"] == 0.0   # a 0-cost row was recorded


def test_meters_tokens_and_usd(monkeypatch):
    conn = _conn()
    # Fake a live provider: client returns text and reports 1000 tokens.
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "LIVE ANSWER")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 1000)
    out = router.complete_text("x", tier="cheap", stage="teach",
                               session_id="s1", conn=conn, fallback="fb")
    assert out == "LIVE ANSWER"
    spend = cost_repo.session_spend(conn, "s1")
    assert spend["tokens"] == 1000
    assert round(spend["usd"], 4) == 0.0004        # 1000/1000 * cheap rate (0.0004)


def test_disabled_tier_raises_before_any_call(monkeypatch):
    conn = _conn()
    called = {"n": 0}
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: called.__setitem__("n", 1))
    with pytest.raises(ValueError):
        router.complete_text("x", tier="reranker", stage="teach",
                             session_id="s1", conn=conn, fallback="fb")
    assert called["n"] == 0                         # never reached the provider


def test_complete_json_meters(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 200)
    out = router.complete_json("x", tier="frontier", stage="digest",
                               session_id="s1", conn=conn, fallback={"ok": False})
    assert out == {"ok": True}
    assert cost_repo.session_spend(conn, "s1")["tokens"] == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'litnav.llm.router'`.

- [ ] **Step 3: Implement `router.py`**

Create `litnav/llm/router.py`:

```python
"""Router — the single metered chokepoint for every open-world LLM call.

Resolves a tier against the registry (refusing disabled/record-only models), calls the underlying
client, reads the per-call token cost, computes USD from the tier rate, and writes a cost_ledger
row. Offline (provider=none) the client returns the caller's fallback with 0 token cost, so a
0-cost row is recorded and budgets are never tripped — determinism preserved.
"""
from __future__ import annotations

import sqlite3

from litnav.llm import client as llm_client
from litnav.llm import registry
from litnav.storage import cost_repo


class BudgetExceeded(RuntimeError):
    """Raised when a session's recorded spend has reached its token budget."""


def _meter(*, conn, session_id, stage, tier, model, usd_per_1k, budget):
    """Record this call's cost; enforce the budget AFTER recording. Returns nothing."""
    tokens = int(llm_client.last_token_cost() or 0)
    usd = round(tokens / 1000 * usd_per_1k, 6)
    if conn is not None:
        cost_repo.record_cost(conn, session_id=session_id, stage=stage, tier=tier, model=model,
                              total_tokens=tokens, usd=usd, cache_hit=False)
    if budget is not None and conn is not None and session_id is not None:
        if cost_repo.session_spend(conn, session_id)["tokens"] >= budget:
            raise BudgetExceeded(
                f"session {session_id!r} reached token budget {budget} (stage={stage})")


def complete_text(prompt: str, *, tier: str, stage: str, fallback: str,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  max_tokens: int = 400, budget: int | None = None) -> str:
    spec = registry.resolve_tier(tier)               # raises if disabled/unknown — before any call
    out = llm_client.complete_text(prompt, fallback=fallback, max_tokens=max_tokens)
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out


def complete_json(prompt: str, *, tier: str, stage: str, fallback: dict,
                  session_id: str | None = None, conn: sqlite3.Connection | None = None,
                  schema_hint: str = "", budget: int | None = None) -> dict:
    spec = registry.resolve_tier(tier)
    out = llm_client.complete_json(prompt, schema_hint=schema_hint, fallback=fallback)
    _meter(conn=conn, session_id=session_id, stage=stage, tier=tier, model=spec["model"],
           usd_per_1k=spec["usd_per_1k"], budget=budget)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_router.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add litnav/llm/router.py tests/test_router.py
git commit -m "feat(cost): router metering chokepoint over llm client"
```

---

## Task 4: Per-session budget cap

**Files:**
- Modify: none (router already accepts `budget`) — this task adds the dedicated budget tests.
- Test: `tests/test_budget.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_budget.py`:

```python
import sqlite3
import pytest
from litnav.storage.schema import init_db
from litnav.llm import router, BudgetExceeded   # re-exported for convenience (added in Step 3)
from litnav.llm import client as llm_client


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_budget_trips_after_spend_reaches_cap(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "ok")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 600)
    # budget=1000; first call records 600 (<1000) -> ok; second reaches 1200 (>=1000) -> raise.
    router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                         fallback="fb", budget=1000)
    with pytest.raises(BudgetExceeded):
        router.complete_text("b", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb", budget=1000)


def test_no_budget_never_trips(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(llm_client, "complete_text", lambda *a, **k: "ok")
    monkeypatch.setattr(llm_client, "last_token_cost", lambda: 10_000)
    for _ in range(5):
        router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb")  # budget=None -> never raises


def test_offline_never_trips_budget(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    conn = _conn()
    for _ in range(100):
        router.complete_text("a", tier="cheap", stage="teach", session_id="s1", conn=conn,
                             fallback="fb", budget=1)   # offline cost is 0 -> never reaches 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_budget.py -q`
Expected: FAIL — `ImportError: cannot import name 'BudgetExceeded' from 'litnav.llm'`.

- [ ] **Step 3: Re-export `router` and `BudgetExceeded` from the package**

In `litnav/llm/__init__.py`, append:

```python
from litnav.llm import router  # noqa: E402,F401
from litnav.llm.router import BudgetExceeded  # noqa: E402,F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_budget.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add litnav/llm/__init__.py tests/test_budget.py
git commit -m "feat(cost): per-session token budget cap (BudgetExceeded)"
```

---

## Task 5: `verify_cost` gate

**Files:**
- Create: `litnav/evaluation/verify_cost.py`
- (No test file — this IS the gate, run manually and in CI like `verify_m0..m3`.)

- [ ] **Step 1: Implement the gate**

Create `litnav/evaluation/verify_cost.py`:

```python
"""G-cost: prove the cost spine — metering records spend, the budget cap fires, and a
record-only model cannot be called. Runs fully offline + with a monkeypatched live provider.
"""
from __future__ import annotations

import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, BudgetExceeded
from litnav.llm import client as llm_client


def main() -> int:
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    # 1) Offline call records a 0-cost row (determinism preserved).
    import os
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    router.complete_text("x", tier="cheap", stage="teach", session_id="s", conn=conn, fallback="fb")
    assert cost_repo.session_spend(conn, "s")["tokens"] == 0
    print("G-cost PASS: offline call recorded at 0 cost")

    # 2) A record-only model cannot be called.
    try:
        router.complete_text("x", tier="reranker", stage="teach", session_id="s", conn=conn,
                             fallback="fb")
        raise SystemExit("G-cost FAIL: record-only model was callable")
    except ValueError:
        print("G-cost PASS: record-only model refused")

    # 3) Metering + budget cap fire with a (faked) live provider.
    llm_client.complete_text = lambda *a, **k: "live"
    llm_client.last_token_cost = lambda: 700
    conn2 = sqlite3.connect(":memory:"); init_db(conn2)
    router.complete_text("a", tier="cheap", stage="teach", session_id="b", conn=conn2,
                         fallback="fb", budget=1000)
    assert cost_repo.session_spend(conn2, "b")["tokens"] == 700
    try:
        router.complete_text("b", tier="cheap", stage="teach", session_id="b", conn=conn2,
                             fallback="fb", budget=1000)
        raise SystemExit("G-cost FAIL: budget did not fire")
    except BudgetExceeded:
        print("G-cost PASS: metering + budget cap fired")

    print("G-cost: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 2: Run the gate**

Run: `python -m litnav.evaluation.verify_cost`
Expected output ends with `G-cost: ALL PASS`.

- [ ] **Step 3: Run the full suite + existing gates (no regressions)**

Run: `python -m pytest -q`
Expected: all prior tests still pass + the 13 new tests (cost_repo 2, registry 4, router 4, budget 3).

Run: `python -m litnav.evaluation.verify_m0` … `verify_m3`
Expected: all four still PASS (the cost spine is additive; nothing in the teach loop changed yet).

- [ ] **Step 4: Commit**

```bash
git add litnav/evaluation/verify_cost.py
git commit -m "feat(cost): verify_cost gate (metering + budget + record-only refusal)"
```

---

## Self-review

**1. Spec coverage (§5 model router & cost governance):**
- Three tiers / registry → Task 2 (`MODEL_REGISTRY`, `cheap`+`frontier` enabled). ✓
- Record-only model-need protocol (incl. non-OpenAI) → Task 2 (`RECORDED_NEEDS`, not resolvable). ✓
- Metering of every call (`cost_ledger`) → Task 1 + Task 3. ✓
- Per-session budget cap → Task 4. ✓
- Escalation gate / caching / precompute → **deferred** (OW-2..OW-6): the *mechanism* (tier param +
  router) is here; escalation policy and semantic cache are later milestones. Noted, not a gap.
- Glass-box live meter → `cost_repo.session_spend()` exists now; the UI panel wiring is OW-6. ✓

**2. Placeholder scan:** none — every step has full code and an exact command.

**3. Type consistency:** `record_cost(... total_tokens=, usd=, cache_hit=)` and
`session_spend()→{tokens, usd}` are used identically in Tasks 1, 3, 5. `resolve_tier()→{model,
usd_per_1k}` consistent across Tasks 2, 3. `router.complete_text/json(tier, stage, fallback,
session_id, conn, budget)` consistent across Tasks 3, 4, 5. ✓

**Out of scope for OW-0 (by design):** input/output token split (blended rate is enough now);
semantic/prompt caching; escalation policy — including the literature review's **pedagogical-error-cost
pricing** (escalate when a wrong correctness judgment is costly, not when tokens are) — which lands in
OW-4; wiring existing teach/assess calls through the router (that migration happens in OW-4 so this
milestone stays additive and green).
