# Phase 0 — LLM Liveness Precondition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Make a live LLM/embed call provably distinguishable from a silent fallback, so every later live gate (and the budget cap) can mean something — `litnav/llm/client.py` currently swallows every exception (`except Exception: return fallback`, `_tls.cost=0`), so a dead provider is indistinguishable from success.

**Architecture:** Add an opt-in **strict mode** (`LITNAV_LLM_STRICT`) to `client.py`: in strict mode a provider error **raises `LivenessError`** instead of returning the fallback; outside strict mode (and always for `provider=none`) behavior is unchanged. Add a per-call `was_live()` signal (true iff a real response was parsed with `tokens>0`). Add a controller-run `verify_liveness` LIVE gate that proves (a) a real call registers live with metered tokens and (b) a forced provider error raises rather than silently falling back. Document the CI live-gate execution contract.

**Tech Stack:** Python, `litnav.llm.client`/`router`/`registry`, `litnav.storage.cost_repo`, pytest.

---

## Design notes
- `was_live()` is intentionally conservative: true only when a real response parsed AND `response.usage.total_tokens > 0`. `provider=none` and the swallowed-exception path both leave it False. A rare real response reporting 0 tokens under-claims liveness (safe).
- Strict mode is **opt-in** so the existing 176 offline tests + gates (which rely on silent fallback at `provider=none`) stay green untouched. `provider=none` NEVER raises (it returns the fallback before the try block).
- The router needs no change to propagate `LivenessError` (it does not wrap the client call in try/except) — but we add a test pinning that contract, and confirm no `cost_ledger` row is written for a raised call.

## File structure
| File | Responsibility |
|---|---|
| `litnav/llm/client.py` (modify) | `LivenessError`, `_strict()`, `was_live()`, strict raise + `_tls.was_live` in all three call paths |
| `litnav/llm/__init__.py` (modify) | re-export `LivenessError` |
| `litnav/evaluation/verify_liveness.py` (create) | LIVE gate: real call is live + forced error raises (skips with a clear message at `provider=none`) |
| `docs/2026-06-20-live-gate-execution-contract.md` (create) | CI execution contract for live gates |
| `tests/test_llm_strict.py` (create) | offline TDD for strict mode + was_live via monkeypatch |

---

## Task 1: client.py strict mode + was_live signal

**Files:** Modify `litnav/llm/client.py`, `litnav/llm/__init__.py`; Create `tests/test_llm_strict.py`.

- [ ] **Step 1: Write the failing test** `tests/test_llm_strict.py`:

```python
import pytest
from litnav.llm import client as c


class _Resp:
    def __init__(self, content, tokens):
        self.choices = [type("Ch", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = type("U", (), {"total_tokens": tokens})()


class _FakeChat:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc
    def create(self, **kw):
        if self._exc:
            raise self._exc
        return self._resp


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self.chat = type("C", (), {"completions": _FakeChat(resp, exc)})()
        self.embeddings = type("E", (), {"create": (lambda **kw: (_ for _ in ()).throw(self._exc)) if exc else (lambda **kw: type("R", (), {"data": [type("D", (), {"embedding": [0.1]})()], "usage": type("U", (), {"total_tokens": 5})()})())})()
        self._exc = exc


def _set(monkeypatch, *, provider="openai", strict=False, resp=None, exc=None):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", provider)
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1" if strict else "")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=resp, exc=exc))


def test_success_sets_was_live_and_tokens(monkeypatch):
    _set(monkeypatch, resp=_Resp('{"ok": true}', 42))
    out = c.complete_json("p", fallback={"ok": False})
    assert out == {"ok": True} and c.was_live() is True and c.last_token_cost() == 42


def test_provider_none_never_live_never_raises(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1")
    assert c.complete_json("p", fallback={"x": 1}) == {"x": 1}
    assert c.was_live() is False


def test_non_strict_error_falls_back(monkeypatch):
    _set(monkeypatch, strict=False, exc=RuntimeError("429"))
    assert c.complete_text("p", fallback="fb") == "fb"
    assert c.was_live() is False


def test_strict_error_raises_liveness(monkeypatch):
    _set(monkeypatch, strict=True, exc=RuntimeError("429"))
    with pytest.raises(c.LivenessError):
        c.complete_text("p", fallback="fb")
```

- [ ] **Step 2: Run, confirm FAIL** — `python -m pytest tests/test_llm_strict.py -v` (LivenessError/was_live not defined).

- [ ] **Step 3: Edit `litnav/llm/client.py`.** Add near the top (after the `_tls` definition):

```python
class LivenessError(RuntimeError):
    """Raised in strict mode when a live LLM/embed call fails instead of silently falling back."""


def _strict() -> bool:
    return os.getenv("LITNAV_LLM_STRICT", "") not in ("", "0", "false", "False")


def was_live() -> bool:
    """True iff the most recent call on this thread parsed a real response with tokens>0
    (provider=none and the silent-fallback path both leave this False)."""
    return bool(getattr(_tls, "was_live", False))
```

In **`complete_json`**: after `_tls.cost = 0` add `_tls.was_live = False`. Change `except Exception:` to `except Exception as e:` and replace `return fallback` in that handler with:
```python
        if _strict():
            raise LivenessError(f"complete_json failed in strict mode: {e}") from e
        return fallback
```
Immediately after `_tls.cost = int(response.usage.total_tokens or 0)` (inside its try/except) and BEFORE `return json.loads(...)`, set the live flag based on the parsed result:
```python
        result = json.loads(response.choices[0].message.content)
        _tls.was_live = _tls.cost > 0
        return result
```
(Replace the existing `return json.loads(response.choices[0].message.content)` line with the three lines above.)

Apply the SAME pattern to **`complete_text`**: `_tls.was_live = False` after `_tls.cost = 0`; capture `as e`; strict-raise in the handler; and after reading `_tls.cost`, set `_tls.was_live = _tls.cost > 0` before returning `response.choices[0].message.content or fallback`.

Apply to **`embed_texts`**: `_tls.was_live = False` after `_tls.cost = 0`; `except Exception as e:` → strict-raise else `return None`; after reading `_tls.cost`, set `_tls.was_live = _tls.cost > 0` before `return [d.embedding for d in response.data]`.

- [ ] **Step 4: Edit `litnav/llm/__init__.py`** — re-export `LivenessError` alongside the existing router/BudgetExceeded re-exports (match the existing import style; e.g. `from litnav.llm.client import LivenessError, was_live`).

- [ ] **Step 5: Run, confirm PASS** — `python -m pytest tests/test_llm_strict.py -v` (4 pass).

- [ ] **Step 6: Regression** — `python -m pytest -q` → expect **180 passed** (176 + 4). Run the five gates (`verify_m1/m2/m3/cost/digest`) → all PASS (strict is opt-in/off by default, so nothing changes). Report real numbers.

- [ ] **Step 7: Commit** (do NOT push):
```bash
git add litnav/llm/client.py litnav/llm/__init__.py tests/test_llm_strict.py
git commit -m "feat(live): client.py strict mode (LivenessError) + was_live() signal"
```

---

## Task 2: verify_liveness LIVE gate + CI execution-contract doc

**Files:** Create `litnav/evaluation/verify_liveness.py`, `docs/2026-06-20-live-gate-execution-contract.md`; add a router-propagation test to `tests/test_llm_strict.py`.

- [ ] **Step 1: Add the router-propagation test** to `tests/test_llm_strict.py`:
```python
def test_router_propagates_liveness_error_and_records_no_cost(monkeypatch):
    import sqlite3
    from litnav.llm import router
    from litnav.storage.schema import init_db
    from litnav.storage import cost_repo
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LITNAV_LLM_STRICT", "1")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(exc=RuntimeError("boom")))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    with pytest.raises(c.LivenessError):
        router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb")
    assert cost_repo.session_spend(conn, "s")["tokens"] == 0  # no cost row for a raised call
```
Run it → confirm PASS (router already propagates; this pins the contract).

- [ ] **Step 2: Create `litnav/evaluation/verify_liveness.py`** (the LIVE gate — run by the controller with a real provider):
```python
"""G-liveness (LIVE): prove a real LLM call is distinguishable from a silent fallback.

Run with a real provider:  LITNAV_LLM_PROVIDER=openai  python -m litnav.evaluation.verify_liveness
At provider=none it SKIPS with a clear message (it cannot test liveness offline).
"""
from __future__ import annotations

import os
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, client as llm_client
from litnav.llm.client import LivenessError


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-liveness SKIP: set LITNAV_LLM_PROVIDER=openai to run this LIVE gate.")
        return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    conn = sqlite3.connect(":memory:"); init_db(conn)

    # 1) a real call registers as live with metered tokens
    out = router.complete_text("Reply with the single word: pong.", tier="cheap",
                               stage="liveness", session_id="live", conn=conn, max_tokens=8)
    assert llm_client.was_live(), "G-liveness FAIL: real call did not register live (tokens=0/fallback)"
    spend = cost_repo.session_spend(conn, "live")
    assert spend["tokens"] > 0, "G-liveness FAIL: no tokens metered on a live call"
    print(f"G-liveness PASS: live call ok (reply={out!r}, tokens={spend['tokens']}, usd={spend['usd']})")

    # 2) a forced provider error RAISES (not silent fallback)
    saved = os.environ.get("LITNAV_LLM_MODEL")
    os.environ["LITNAV_LLM_MODEL"] = "this-model-does-not-exist-zzz"
    try:
        router.complete_text("x", tier="cheap", stage="liveness", session_id="live2",
                             conn=conn, fallback="fb")
        print("G-liveness FAIL: bad model did NOT raise in strict mode (silent fallback)")
        return 1
    except LivenessError:
        print("G-liveness PASS: strict mode raised on provider error (no silent fallback)")
    finally:
        if saved is None:
            os.environ.pop("LITNAV_LLM_MODEL", None)
        else:
            os.environ["LITNAV_LLM_MODEL"] = saved

    print("G-liveness: ALL PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 3: Create `docs/2026-06-20-live-gate-execution-contract.md`:**
```markdown
# Live-Gate Execution Contract

Live gates (`verify_liveness`, future `verify_digest_live`, `verify_cost_live`) make REAL,
non-deterministic, billed, network calls. They are NOT offline CI gates. Rules:

- **Provider/key:** run with `LITNAV_LLM_PROVIDER=openai` and the key from `.env` (never committed,
  never printed). `provider=none` ⇒ the gate SKIPS with a clear message.
- **Strict liveness:** every live gate sets `LITNAV_LLM_STRICT=1` and asserts `was_live()` (tokens>0,
  not a fallback) before any capability assertion — a broken/skipped provider can never look like a pass.
- **Budget:** each live gate runs on a tiny fixed real input and passes a `budget` so the per-run spend
  is hard-capped; the gate asserts `cost_ledger` spend > 0 AND ≤ budget.
- **Outage policy:** on a provider outage the gate SKIPS with a loud warning (exit 0 + explicit SKIP
  line) — it must never silently pass and never flake-fail a merge.
- **Cost surfaced:** every live gate prints the metered `cost_ledger` (tokens + USD) it incurred.
- **Frontier de-dup:** before a live gate that judges edges, the double `_judge` call must be
  de-duplicated (see digest pipeline NOTE) so high-impact edges are not billed twice.
```

- [ ] **Step 4: Offline sanity** — `python -m litnav.evaluation.verify_liveness` (with `LITNAV_LLM_PROVIDER` unset/none) prints the SKIP line and exits 0. `python -m pytest tests/test_llm_strict.py -v` → 5 pass. `python -m pytest -q` → **181 passed**. Report real numbers.

- [ ] **Step 5: Commit** (do NOT push):
```bash
git add litnav/evaluation/verify_liveness.py docs/2026-06-20-live-gate-execution-contract.md tests/test_llm_strict.py
git commit -m "feat(live): verify_liveness LIVE gate + live-gate execution contract"
```

---

## Controller live verification (NOT a subagent task)
After both tasks land, the **controller** runs the live gate with a real provider and produces the three-part report (live usage report + cost table + evaluation framework):
```bash
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_liveness
```
Then read `cost_ledger` for the run, tabulate tokens/USD, and assess (optimize? action points?). Per the post-cycle report standard.

## Self-Review
- Spec coverage: strict-raise (Task 1), was_live (Task 1), router propagation + no-cost-on-raise (Task 2), LIVE gate proving live-vs-fallback (Task 2), CI contract doc (Task 2). ✅
- Placeholder scan: none — all code shown. The `_FakeClient.embeddings` lambda is only needed if an embed test is added; client tests here use complete_json/complete_text, so it is inert but harmless. ✅
- Type consistency: `LivenessError`, `was_live()`, `_strict()` names used identically across client/__init__/gate/tests. ✅
- No new enabled model; strict mode opt-in so the 176 offline tests stay green. ✅
