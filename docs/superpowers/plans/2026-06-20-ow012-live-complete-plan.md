# OW-0..2 Live-Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.
> Phase 0 (liveness precondition) is DONE (`LITNAV_LLM_STRICT`, `was_live()`, `verify_liveness`).

**Goal:** Make OW-0 (cost spine), OW-1 (data model), OW-2 (digest) genuinely **live-complete**: a real digest of real sources produces a real graph (LLM-proposed edges), evidence resolves, the cache re-reads, both models do their real jobs, and LIVE gates (not golden fixtures) validate structure + quality + real metered cost.

**Architecture:** (1) OW-1 storage so live evidence + cache work: insert `papers`/`paper_chunks` for digested sources; tag concepts/edges with `slice_key`; cache hit re-reads the slice graph; cache keyed by model. (2) Phase-1 capability: `edges.py` asks the LLM to **propose** edges over its own extracted concepts (candidate = offline fallback only); de-dup the frontier judge; shuffle the quality sample; live quiz-seed gen. (3) OW-0 + Phase-2 gates: `verify_cost_live` (budget cap fires on real spend; ledger records the actual model), `verify_digest_live` (structure + quality threshold + real cost, liveness-asserted), demote the golden gate to a labeled unit test.

**Tech Stack:** Python, `litnav.llm.{client,router,registry}`, `litnav.storage.{schema,repo,openworld_repo,cost_repo}`, `litnav.digest.*`, pytest. Live gates run with `LITNAV_LLM_PROVIDER=openai` + `LITNAV_LLM_STRICT=1` per `docs/2026-06-20-live-gate-execution-contract.md`.

**Out of scope (recorded, deferred to OW-4 ASSESS):** `learner_goal` slug↔ID reconciliation (gap ⑫); full quiz distractors/IRT/Bloom difficulty. Digest emits *seed* questions only.

---

## Conventions
- Offline determinism is kept ONLY for safety/math (formulas, schema, budget state machine). Capability is proven by the LIVE gates, run by the controller. A green offline run is NOT capability evidence.
- Every task: TDD offline (failing test → implement → pass), regression `pytest -q` + the 5 offline gates green, commit (no push; controller pushes). Report REAL counts.
- Baseline at plan start: **182 passed**.

---

## Task 1: papers + paper_chunks for digested sources (evidence FKs resolve)

**Files:** Modify `litnav/storage/repo.py`, `litnav/digest/pipeline.py`; Test `tests/test_digest_evidence.py`.

Currently the pipeline uses synthetic chunk ids (`c0,c1`) that are never inserted, so `keypoints.evidence_chunk_id`/edge evidence dangle and `repo.get_chunk_text` returns "". Insert real rows.

- [ ] **Step 1: failing test** `tests/test_digest_evidence.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline


CANDIDATE = {
    "concepts": [{"slug": "a", "name": "A", "domain": "d", "frontier_flag": None}],
    "keypoints": [{"kp_id": "kp_a", "concept_slug": "a", "name": "k", "objective": "o",
                   "evidence_chunk_id": "c0", "bloom_level": "recall"}],
    "prereq_edges": [], "similarity_edges": [], "quiz_seeds": [], "judge_labels": {},
}


def test_digest_inserts_paper_chunks_so_evidence_resolves(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    di = DigestInput("d", [SourceDoc("arxiv", "2210.00001", "T", "http://x", ["chunk zero text", "chunk one text"])], [])
    pipeline.digest(di, conn=c, candidate=CANDIDATE, session_id="s")
    # a papers row exists for the source, with source_type/url
    row = c.execute("SELECT source_type, url FROM papers WHERE arxiv_id='2210.00001'").fetchone()
    assert row == ("arxiv", "http://x")
    # paper_chunks c0/c1 exist with the real text
    assert repo.get_chunk_text(c, "c0") == "chunk zero text"
    assert repo.get_chunk_text(c, "c1") == "chunk one text"
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: add repo writers** in `litnav/storage/repo.py`:
```python
def create_paper(conn: sqlite3.Connection, *, arxiv_id: str | None, title: str,
                 source_type: str | None = None, url: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO papers (arxiv_id, title, source_type, url) VALUES (?,?,?,?)",
        (arxiv_id, title, source_type, url),
    )
    conn.commit()
    return int(cur.lastrowid)


def create_paper_chunk(conn: sqlite3.Connection, chunk_id: str, paper_id: int,
                       concept_id: int | None, text: str, chunk_index: int = 0,
                       section: str = "digested") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO paper_chunks "
        "(id, paper_id, concept_id, section, chunk_index, text) VALUES (?,?,?,?,?,?)",
        (chunk_id, paper_id, concept_id, section, chunk_index, text),
    )
    conn.commit()
```
(Confirm `get_chunk_text` already exists and returns the row text or "".)

- [ ] **Step 4: pipeline inserts them.** In `litnav/digest/pipeline.py`, add a helper and call it at the START of `_write_graph` (before concepts), building the global `c0,c1,...` ids exactly like `edges.py`:
```python
def _write_sources(conn, di) -> None:
    """Insert a papers row per source + paper_chunks rows (global c0,c1,... ids) so digested
    evidence_chunk_id references resolve to real text."""
    idx = 0
    for s in di.sources:
        pid = repo.create_paper(conn, arxiv_id=s.source_id, title=s.title,
                                source_type=s.source_type, url=s.url)
        for ci, text in enumerate(s.chunks):
            repo.create_paper_chunk(conn, f"c{idx}", pid, None, text, chunk_index=ci)
            idx += 1
```
Call `_write_sources(conn, di)` as the first line of `_write_graph`.

- [ ] **Step 5: run** `python -m pytest tests/test_digest_evidence.py -v` → PASS. Then `pytest -q` → **183 passed**; 5 gates green (verify_digest still passes — chunk ids now resolve, which only helps). Report real numbers.

- [ ] **Step 6: commit** `feat(ow1-live): insert papers+paper_chunks in digest so evidence FKs resolve`.

---

## Task 2: slice_key tagging + model-keyed cache + cache-hit re-read

**Files:** Modify `litnav/storage/schema.py`, `litnav/storage/repo.py`, `litnav/storage/openworld_repo.py`, `litnav/digest/pipeline.py`; Test `tests/test_digest_cache_reread.py`.

- [ ] **Step 1: failing test** `tests/test_digest_cache_reread.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline

CAND = {
    "concepts": [{"slug": "a", "name": "A", "domain": "d", "frontier_flag": None},
                 {"slug": "b", "name": "B", "domain": "d", "frontier_flag": None}],
    "keypoints": [], "prereq_edges": [
        {"prereq_slug": "a", "target_slug": "b", "evidence_chunks": ["c0"],
         "max_strength": "explicit_assertion", "multi_paper": False}],
    "similarity_edges": [], "quiz_seeds": [], "judge_labels": {"a->b": True},
}

def _di():
    return DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["t0", "t1"])], [])

def test_cache_hit_rereads_populated_graph(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    r1 = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    assert r1.cache_hit is False and len(r1.edges) >= 1
    r2 = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    assert r2.cache_hit is True
    assert {x["slug"] for x in r2.concepts} == {"a", "b"}      # re-read, NOT empty
    assert any(e["edge_type"] == "prerequisite" for e in r2.edges)

def test_model_key_change_invalidates_cache(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    c = sqlite3.connect(":memory:"); init_db(c)
    pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s")
    # simulate a different model config -> different model_key -> miss (re-digest, not a hit)
    r = pipeline.digest(_di(), conn=c, candidate=CAND, session_id="s", model_key="other-model")
    assert r.cache_hit is False
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: schema migrations.** In `litnav/storage/schema.py` `init_db` migration list, append:
```python
        "ALTER TABLE concepts ADD COLUMN slice_key TEXT",
        "ALTER TABLE concept_edges ADD COLUMN slice_key TEXT",
        "ALTER TABLE digest_cache ADD COLUMN model_key TEXT",
```

- [ ] **Step 4: repo + openworld_repo.**
In `repo.py`, give `create_concept` and `record_edge` an optional `slice_key`:
```python
# create_concept: add param `slice_key: str | None = None`, include column in INSERT
#   "INSERT OR IGNORE INTO concepts (id, slug, name, frontier_flag, source, domain, slice_key) VALUES (?,?,?,?,?,?,?)"
# record_edge: add param `slice_key: str | None = None`, include column in INSERT
#   "... (prereq_concept, target_concept, edge_type, source, confidence, evidence, slice_key) VALUES (?,?,?,?,?,?,?)"
```
Add a slice-graph reader:
```python
def get_slice_graph(conn: sqlite3.Connection, slice_key: str) -> dict:
    """Reconstruct the digested graph for a slice: concepts + edges tagged with slice_key."""
    crows = conn.execute(
        "SELECT slug, name, domain, frontier_flag FROM concepts WHERE slice_key=?", (slice_key,)
    ).fetchall()
    concepts = [{"slug": r[0], "name": r[1], "domain": r[2], "frontier_flag": r[3]} for r in crows]
    id_to_slug = {r[0]: r[1] for r in
                  conn.execute("SELECT id, slug FROM concepts WHERE slice_key=?", (slice_key,))}
    erows = conn.execute(
        "SELECT prereq_concept, target_concept, edge_type, confidence, evidence "
        "FROM concept_edges WHERE slice_key=?", (slice_key,)
    ).fetchall()
    import json
    edges = [{"prereq_slug": id_to_slug.get(r[0]), "target_slug": id_to_slug.get(r[1]),
              "edge_type": r[2], "confidence": r[3],
              "evidence": json.loads(r[4]) if r[4] else []} for r in erows]
    return {"concepts": concepts, "edges": edges}
```
In `openworld_repo.py`, extend cache with `model_key`:
```python
# cache_put(conn, slice_key, *, graph_version=1, human_checked=False, model_key=None):
#   include model_key in the INSERT and the ON CONFLICT update.
# cache_get: also SELECT model_key and return it in the dict.
```

- [ ] **Step 5: pipeline.** In `litnav/digest/pipeline.py`:
- Add a model-key helper:
```python
import os
def _model_key() -> str:
    return os.getenv("LITNAV_LLM_PROVIDER", "none") + "|" + os.getenv("LITNAV_LLM_MODEL", "gpt-4o-mini")
```
- `digest(...)` gains `model_key: str | None = None`; resolve `mk = model_key or _model_key()`.
- Cache-hit branch: `cached = openworld_repo.cache_get(conn, key)`; if `cached and cached["status"]=="cached" and cached.get("model_key")==mk`: re-read and return populated:
```python
        g = repo.get_slice_graph(conn, key)
        return DigestResult(di.domain_key, g["concepts"], g["edges"], [], [], [],
                            edge_accuracy=1.0, cache_hit=True)
```
  (else fall through to a full digest — different model_key ⇒ miss.)
- `_write_graph`: thread `slice_key=key` into `repo.create_concept(...)` and `repo.record_edge(...)`.
- `cache_put`: pass `model_key=mk`.

- [ ] **Step 6: run** `python -m pytest tests/test_digest_cache_reread.py -v` → PASS; update `tests/test_digest_pipeline.py` if its cache-hit test asserted empty (`res2.concepts == []`) — it must now assert the re-read is populated. `pytest -q` → expect **~185 passed** (183 + 2, minus any updated assertion). Report real. 5 gates green (verify_digest unaffected — single slice).

- [ ] **Step 7: commit** `feat(ow1-live): slice_key tagging + model-keyed cache + cache-hit re-read`.

---

## Task 3: live edge GENERATION over extracted concepts (the core capability)

**Files:** Modify `litnav/digest/edges.py`, `litnav/digest/verify.py`; Test `tests/test_digest_edge_gen.py`.

The LLM must PROPOSE edges over the concepts it extracted; the candidate is offline fallback ONLY.

- [ ] **Step 1: failing test** `tests/test_digest_edge_gen.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import edges
from litnav.llm import router

CONCEPTS = [{"slug": "tool_use", "name": "Tool Use", "domain": "d", "frontier_flag": None},
            {"slug": "react", "name": "ReAct", "domain": "d", "frontier_flag": None}]
CAND = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "react",
        "evidence_chunks": ["c0"], "max_strength": "weak_hint", "multi_paper": False}],
        "similarity_edges": []}

def _di():
    return DigestInput("d", [SourceDoc("arxiv", "x", "X", None, ["c0 text", "c1 text"])], [])

def test_live_llm_proposes_edges_over_extracted_slugs(monkeypatch):
    # live: the LLM proposes an edge between the EXTRACTED slugs (tool_use->react), strong evidence
    proposed = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "react",
                "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False}],
                "similarity_edges": []}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: proposed)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    pe = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert (pe["prereq_slug"], pe["target_slug"]) == ("tool_use", "react")
    assert pe["confidence"] == 0.75   # 1 chunk, explicit (from the PROPOSAL, not the candidate's weak_hint)

def test_proposed_edge_with_unknown_endpoint_is_dropped(monkeypatch):
    proposed = {"prereq_edges": [{"prereq_slug": "tool_use", "target_slug": "GHOST",
                "evidence_chunks": ["c0"], "max_strength": "explicit_assertion", "multi_paper": False}],
                "similarity_edges": []}
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: proposed)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    assert out == []   # GHOST not an extracted slug -> dropped

def test_offline_falls_back_to_candidate(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")   # router returns the fallback (candidate)
    c = sqlite3.connect(":memory:"); init_db(c)
    out = edges.build_edges(_di(), CONCEPTS, candidate=CAND, session_id="s", conn=c)
    pe = [e for e in out if e["edge_type"] == "prerequisite"][0]
    assert pe["confidence"] == 0.55   # candidate's weak_hint, 1 chunk
```

- [ ] **Step 2: run, confirm FAIL.**

- [ ] **Step 3: implement.** In `litnav/digest/edges.py`, add a proposal seam and route `build_edges` through it. Replace the two `for e in candidate.get(...)` sources with proposed lists:
```python
def _propose_edges(concepts: list[dict], by_chunk: dict, candidate: dict, *,
                   session_id, conn, budget) -> dict:
    """LLM proposes prereq + similarity edges over the EXTRACTED concept slugs (live);
    offline (provider=none) router returns the candidate as fallback. Endpoints are constrained
    to the given slugs in the prompt; build_edges still validates them post-hoc."""
    slug_lines = "\n".join(f"- {c['slug']}: {c.get('name', c['slug'])}" for c in concepts)
    chunks_txt = "\n".join(f"[{cid}] {txt}" for cid, txt in by_chunk.items())
    prompt = (
        "Given these concepts extracted from the evidence, propose edges BETWEEN THEM ONLY.\n"
        "A prerequisite edge means the prereq concept must be understood before the target.\n"
        "A similarity edge links two closely related concepts.\n"
        f"Concepts (use these slugs as endpoints, nothing else):\n{slug_lines}\n\n"
        f"Evidence chunks (cite their ids):\n{chunks_txt}\n\n"
        'Respond JSON: {"prereq_edges": [{"prereq_slug","target_slug","evidence_chunks":[ids],'
        '"max_strength":"weak_hint|general_statement|explicit_assertion","multi_paper":bool}], '
        '"similarity_edges": [{"a_slug","b_slug","evidence_chunks":[ids],"max_strength","multi_paper":bool}]}'
    )
    fallback = {"prereq_edges": candidate.get("prereq_edges", []),
                "similarity_edges": candidate.get("similarity_edges", [])}
    result = router.complete_json(prompt, tier="cheap", stage="digest", fallback=fallback,
                                  session_id=session_id, conn=conn, budget=budget)
    if not isinstance(result, dict):
        return fallback
    return {"prereq_edges": result.get("prereq_edges") or [],
            "similarity_edges": result.get("similarity_edges") or []}
```
In `build_edges`: after computing `by_chunk` and `slugs`, call `proposed = _propose_edges(concepts, by_chunk, candidate, session_id=..., conn=..., budget=...)`, then iterate `proposed["prereq_edges"]` and `proposed["similarity_edges"]` (instead of `candidate.get(...)`). Keep the existing endpoint guards (`if prereq_slug not in slugs ...: continue`) and evidence handling, BUT also drop edges whose `evidence_chunks` contain ids not in `by_chunk` (clean to the real subset; if empty after cleaning, skip the edge). Validate each `max_strength` against `_VALID_STRENGTH` (default `general_statement` if invalid). Everything else (induced_confidence, high_impact, similarity cosine) stays.

- [ ] **Step 4: fix `verify.py::_judge`** so an unknown key does not silently count as a genuine prerequisite when live. Change the final line to distinguish: in live (a real bool came back) use it; only offline fall back to labels, and default UNKNOWN offline keys to **False** (conservative — an unverified edge gets downgraded, not rubber-stamped):
```python
    val = result.get("is_prerequisite") if isinstance(result, dict) else None
    if isinstance(val, bool):
        return val
    return bool(judge_labels.get(key, False))   # was True; unknown -> not a verified prereq
```
Update any offline test/fixture that relied on default-True (the OW-2 golden fixture sets explicit `judge_labels`, so it is unaffected — verify).

- [ ] **Step 5: run** `python -m pytest tests/test_digest_edge_gen.py tests/test_digest_edges.py tests/test_digest_verify.py -v` → PASS. `pytest -q` → report real. Run `verify_digest` — it must still PASS (offline the proposal falls back to the candidate, so the golden graph is unchanged; the `_judge` default flip is covered because the fixture provides explicit labels). If verify_digest FAILS, investigate (do not weaken it).

- [ ] **Step 6: commit** `feat(ow2-live): LLM proposes edges over extracted concepts (candidate=offline fallback); judge unknown-key=False`.

---

## Task 4: frontier judge de-dup + shuffled quality sample + live quiz-seed gen

**Files:** Modify `litnav/digest/verify.py`, `litnav/digest/pipeline.py`; Test `tests/test_digest_quality.py`.

- [ ] **Step 1: failing test** `tests/test_digest_quality.py`:
```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.digest import verify, pipeline
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.llm import router

def test_judge_called_once_per_edge(monkeypatch):
    calls = {"n": 0}
    def fake(*a, **k):
        calls["n"] += 1
        return {"is_prerequisite": True}
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai"); monkeypatch.setenv("LITNAV_LLM_STRICT", "")
    monkeypatch.setattr(router, "complete_json", fake)
    edges = [{"prereq_slug": "a", "target_slug": "b", "edge_type": "prerequisite",
              "evidence": ["c0"], "confidence": 0.75, "high_impact": True}]
    c = sqlite3.connect(":memory:"); init_db(c)
    acc, verified = verify.verify_pass(edges, judge_labels={}, session_id="s", conn=c)
    assert calls["n"] == 1            # judged exactly once (not twice)
    assert acc == 1.0 and verified[0][0]["edge_type"] == "prerequisite"
```

- [ ] **Step 2: run, confirm FAIL** (`verify_pass` not defined).

- [ ] **Step 3: add a combined `verify_pass`** to `litnav/digest/verify.py` that judges each high-impact edge ONCE and returns both the accuracy metric and the verified/unverified split, so the pipeline stops calling `_judge` twice. Keep `edge_accuracy`/`verify_edges` for back-compat but have the pipeline call `verify_pass`:
```python
import random

def verify_pass(edges, *, judge_labels, session_id, conn, budget=None, sample_n=10):
    """Judge each prereq edge ONCE; return (edge_accuracy, (out, unverified)).
    edge_accuracy is over a SHUFFLED post-downgrade sample of prereq edges."""
    verdict: dict[int, bool] = {}
    def judged(i, e):
        if i not in verdict:
            verdict[i] = _judge(e, judge_labels, session_id=session_id, conn=conn, budget=budget)
        return verdict[i]
    out, unverified = [], []
    for i, e in enumerate(edges):
        e = dict(e)
        if e["edge_type"] != "prerequisite":
            e["verified"] = True; out.append(e); continue
        ok = e["confidence"] >= VERIFY_THRESHOLD
        if ok and e.get("high_impact"):
            ok = judged(i, e)
        if ok:
            e["verified"] = True
        else:
            e["edge_type"] = "similarity"; e["verified"] = False; unverified.append(e)
        out.append(e)
    kept = [e for e in out if e["edge_type"] == "prerequisite"]
    sample = kept[:]
    random.Random(len(kept)).shuffle(sample)   # deterministic-seed shuffle (no Date/rand global)
    sample = sample[:sample_n]
    if not sample:
        acc = 1.0
    else:
        agreed = sum(1 for e in sample
                     if verdict.get(out.index(e), judge_labels.get(
                         f"{e['prereq_slug']}->{e['target_slug']}", False)))
        acc = round(agreed / len(sample), 4)
    return acc, (out, unverified)
```
> Note: accuracy is now measured POST-downgrade on the surviving prereq edges (the edges we actually teach from), reusing the single judge verdict — no second frontier call. `random.Random(seed)` keeps it deterministic for the offline gate.

- [ ] **Step 4: pipeline uses `verify_pass`** and live quiz-seeds. In `litnav/digest/pipeline.py`:
- Replace the separate `edge_accuracy(...)` + `verify_edges(...)` calls with `accuracy, (verified, unverified) = verify_mod.verify_pass(scored, judge_labels=labels, session_id=session_id, conn=conn, budget=budget)`.
- Add live quiz-seed generation (cheap tier; candidate fallback) — a thin helper `_propose_quiz_seeds(concepts, by_chunk, candidate, ...)` mirroring `_propose_edges`: prompt for one short seed question+answer per concept, JSON `{"quiz_seeds":[{concept_slug,question,answer_key,bloom_level}]}`, fallback `candidate.get("quiz_seeds", [])`; drop seeds whose `concept_slug` is not extracted. Replace `quiz_seeds = candidate.get("quiz_seeds", [])` with the proposed list.

- [ ] **Step 5: run** the quality test + `tests/test_digest_pipeline.py` + `verify_digest` → all PASS. `pytest -q` → report real. (Golden gate: with explicit judge_labels and offline fallback, `verify_pass` reproduces the same downgrade/accuracy — verify `edge_accuracy=0.5`, `unverified=1` still hold; adjust `verify_digest.py` to call/expect `verify_pass` semantics if needed, keeping the golden numbers.)

- [ ] **Step 6: commit** `feat(ow2-live): single-judge verify_pass + shuffled post-downgrade accuracy + live quiz-seed gen`.

---

## Task 5: OW-0 live confirm — verify_cost_live + ledger records the actual model (A0b)

**Files:** Modify `litnav/llm/client.py`, `litnav/llm/router.py`; Create `litnav/evaluation/verify_cost_live.py`; Test add to `tests/test_router.py` (or `tests/test_llm_strict.py`).

- [ ] **Step 1: A0b — client exposes the actual model; router meters it.** In `client.py`: in each call set `_tls.model` to the model actually sent (e.g. `_tls.model = model` for chat, `_tls.model = _embed_model()` for embed) right before/after the request; add `def last_model() -> str | None: return getattr(_tls, "model", None)`. In `router.py` `_meter`, change `model=spec["model"]` callers to record the actual model: compute `model = llm_client.last_model() or spec["model"]` and pass that to `cost_repo.record_cost`. Add a failing test first:
```python
def test_ledger_records_actual_model(monkeypatch):
    import sqlite3
    from litnav.llm import router, client as c
    from litnav.storage.schema import init_db
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai"); monkeypatch.setenv("LITNAV_LLM_MODEL", "gpt-4o-mini-2024")
    monkeypatch.setattr(c, "_client", lambda: _FakeClient(resp=_Resp("hi", 10)))  # reuse fakes
    conn = sqlite3.connect(":memory:"); init_db(conn)
    router.complete_text("p", tier="cheap", stage="x", session_id="s", conn=conn, fallback="fb")
    m = conn.execute("SELECT model FROM cost_ledger WHERE session_id='s'").fetchone()[0]
    assert m == "gpt-4o-mini-2024"   # the actual env model, not the registry's "gpt-4o-mini"
```
(Place the fakes import/use consistent with the test file you add to.)

- [ ] **Step 2: run, confirm FAIL; implement; confirm PASS.** Keep `verify_cost` (offline) green.

- [ ] **Step 3: create `litnav/evaluation/verify_cost_live.py`** — LIVE gate (skips at provider=none):
```python
"""G-cost-live (LIVE): prove metering + budget cap work on REAL spend. Skips at provider=none."""
from __future__ import annotations
import os, sqlite3
from litnav.storage.schema import init_db
from litnav.storage import cost_repo
from litnav.llm import router, client as llm_client, BudgetExceeded

def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-cost-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    conn = sqlite3.connect(":memory:"); init_db(conn)
    # 1) a real metered call: tokens>0, usd>0, model recorded
    router.complete_text("Say hi.", tier="cheap", stage="costlive", session_id="cl",
                         conn=conn, fallback="x", max_tokens=8, budget=100000)
    assert llm_client.was_live(), "G-cost-live FAIL: call not live"
    sp = cost_repo.session_spend(conn, "cl"); assert sp["tokens"] > 0 and sp["usd"] > 0
    print(f"G-cost-live PASS: live spend tokens={sp['tokens']} usd={sp['usd']}")
    # 2) a real embed meters tokens
    v = router.embed_texts(["alpha", "beta"], stage="costlive", session_id="cl", conn=conn)
    assert v is not None, "G-cost-live FAIL: embed returned None live"
    print("G-cost-live PASS: live embed metered")
    # 3) budget cap fires on REAL accumulating spend
    fired = False
    try:
        for _ in range(50):
            router.complete_text("Write two sentences about agents.", tier="cheap",
                                 stage="costlive", session_id="cap", conn=conn, fallback="x",
                                 max_tokens=64, budget=120)   # tiny budget -> must trip
    except BudgetExceeded:
        fired = True
    assert fired, "G-cost-live FAIL: budget cap never fired on real spend"
    print("G-cost-live PASS: budget cap fired on real spend")
    print("G-cost-live: ALL PASS"); return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: offline sanity** — `verify_cost_live` at provider=none prints SKIP, exit 0. `pytest -q` → report real. `verify_cost` (offline) green.

- [ ] **Step 5: commit** `feat(ow0-live): ledger records actual model (A0b) + verify_cost_live gate`.

---

## Task 6: verify_digest_live harness + demote the golden gate

**Files:** Create `litnav/evaluation/verify_digest_live.py`; Modify `litnav/evaluation/verify_digest.py` (label as non-capability) + `data/seed/digest_golden_graph.json` (quarantine header); Modify `litnav/digest/SKILL.md`.

- [ ] **Step 1: create `litnav/evaluation/verify_digest_live.py`** — the LIVE capability gate (skips at provider=none). It digests the fixture's REAL chunks LIVE and asserts structure + quality + cost:
```python
"""G-digest-live (LIVE): prove the digest CAPABILITY on real LLM output. Skips at provider=none.

Asserts liveness + structural invariants (edges over EXTRACTED slugs, evidence resolves, confidence
rule-computed, downgrades flagged) + a quality threshold + real metered cost <= budget.
"""
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path
from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.nodes.induce import induced_confidence
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.llm import client as llm_client

_FIX = Path("data/seed/digest_sources_fixture.json")
_FLOOR = 0.5   # quality floor (judge-agreement on surviving prereq edges)
_BUDGET = 20000

def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("G-digest-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    raw = json.loads(_FIX.read_text(encoding="utf-8"))
    di = DigestInput(raw["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in raw["sources"]], raw.get("target_slugs", []))
    conn = sqlite3.connect(":memory:"); init_db(conn)
    res = pipeline.digest(di, conn=conn, candidate=raw["candidate"], session_id="dl", budget=_BUDGET)

    assert llm_client.was_live(), "FAIL: digest did not run live"
    spend = cost_repo.session_spend(conn, "dl")
    assert spend["tokens"] > 0 and spend["usd"] <= 999, "FAIL: no real spend recorded"
    print(f"G-digest-live PASS: live (tokens={spend['tokens']}, usd={spend['usd']})")

    slugs = {c["slug"] for c in res.concepts}
    assert len(slugs) >= 2, f"FAIL: <2 concepts extracted ({slugs})"
    # every edge endpoint is a concept actually extracted this run
    for e in res.edges:
        assert e["prereq_slug"] in slugs and e["target_slug"] in slugs, f"FAIL: edge off-slugs {e}"
    assert len(res.edges) > 0, "FAIL: zero edges from >=2 concepts (the OW-2 bug)"
    # evidence resolves to non-empty text; confidence is rule-recomputable
    for e in res.edges:
        for cid in e["evidence"]:
            assert repo.get_chunk_text(conn, cid), f"FAIL: evidence {cid} resolves empty"
    for uv in res.unverified_edges:
        assert uv["edge_type"] == "similarity", "FAIL: unverified edge not downgraded"
    print(f"G-digest-live PASS: {len(slugs)} concepts, {len(res.edges)} edges, all grounded")

    assert res.edge_accuracy >= _FLOOR, f"FAIL: edge_accuracy {res.edge_accuracy} < floor {_FLOOR}"
    assert spend["usd"] <= 1.0, f"FAIL: cost {spend['usd']} over sane bound"
    print(f"G-digest-live PASS: edge_accuracy={res.edge_accuracy} >= {_FLOOR}; cost ok")
    print("G-digest-live: ALL PASS"); return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 2: demote the golden gate.** In `litnav/evaluation/verify_digest.py`, update the module docstring to: `"""DETERMINISM/SCHEMA UNIT GATE — NOT capability evidence. Validates the confidence formula, downgrade rule, PK-collision ordering, slice_key, and cache plumbing offline. The CAPABILITY is proven by verify_digest_live (real LLM). See docs/2026-06-20-open-world-live-first-reaudit.md."""`. In `data/seed/digest_golden_graph.json` add a top-level `"_note": "determinism fixture — NOT live capability evidence; see verify_digest_live"`. (Adjust the gate's JSON read to ignore the `_note` key.)

- [ ] **Step 3: update `litnav/digest/SKILL.md`** — change the "Offline determinism" line so it says the OFFLINE gate is a determinism/schema check and **`verify_digest_live` (real provider) is the capability gate**; `digest-demo` stays the offline smoke.

- [ ] **Step 4: offline sanity** — `verify_digest_live` at provider=none prints SKIP, exit 0. `verify_digest` still PASS (golden unchanged besides the ignored `_note`). `pytest -q` → report real. All 5 offline gates green.

- [ ] **Step 5: commit** `feat(ow2-live): verify_digest_live capability gate + demote golden gate to determinism unit test`.

---

## Controller live verification (NOT a subagent task) → the final report
After all 6 tasks land, the **controller** runs the LIVE gates with a real provider and produces the consolidated three-part report:
```bash
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_cost_live
LITNAV_LLM_PROVIDER=openai python -m litnav.evaluation.verify_digest_live
```
Then read `cost_ledger`, tabulate tokens/USD by stage+model (both gpt-4o-mini AND gpt-4o now appear), evaluate model adequacy (edge proposal + judge), and record action points. Per the post-cycle report standard. This is the **OW-0..2 live-complete** node.

## Self-Review
- OW-0: A0b (actual model) + verify_cost_live (budget fires on real spend) — Task 5. Phase-0 strict already fixed the $0-degradation hole. ✅
- OW-1: papers/paper_chunks (Task 1), slice_key + model-keyed cache + re-read (Task 2). ⑫ goal reconciliation explicitly deferred to OW-4. ✅
- OW-2: live edge-gen + judge fix (Task 3), single-judge + shuffled accuracy + live quiz-seeds (Task 4), verify_digest_live + demote golden (Task 6). ✅
- Type consistency: `_propose_edges`/`verify_pass`/`get_slice_graph`/`last_model`/`create_paper(_chunk)` names used identically across tasks; `model_key` threaded through cache_get/put/digest. ✅
- Live gates assert `was_live()` first (no dead-provider pass), run budget-capped, skip at provider=none — per the execution contract. ✅
- No new enabled model; offline suite stays green (capability seams fall back to candidate at provider=none). ✅
