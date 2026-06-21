# OW-1 Data Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Extend the SQLite schema for the open-world stages — similarity edges, learner goal, FSRS
review queue, per-item distractors/IRT difficulty, paper source provenance, learner IRT ability, and
the demand-driven digest cache — plus repo writers for the three new tables, all additive and
back-compatible.

**Architecture:** Edit the `DDL` string in `litnav/storage/schema.py` (fresh DBs) and add idempotent
`ALTER TABLE ... ADD COLUMN` lines to `init_db()` (existing file DBs), mirroring the pattern already
there. New per-table writers go in a focused `litnav/storage/openworld_repo.py` (like `cost_repo.py`).

**Tech Stack:** Python 3.12, sqlite3, pytest. Reuses `litnav/storage/schema.py` (`DDL`, `init_db`).

**Spec:** [open-world architecture §4](2026-06-20-open-world-architecture-spec.md).

---

## File structure
- Modify: `litnav/storage/schema.py` — add columns + CHECK values + 3 new tables to `DDL`; add
  idempotent `ALTER` migrations to `init_db()`.
- Create: `litnav/storage/openworld_repo.py` — writers for `learner_goal`, `review_queue`,
  `digest_cache`.
- Test: `tests/test_ow1_schema.py`, `tests/test_openworld_repo.py`.

Notes / decisions:
- `quiz_items.difficulty` is already `INTEGER`; **do not change its type** (SQLite can't ALTER a
  column type without table rebuild). Add **`irt_b REAL`** for the IRT difficulty parameter and
  **`distractors_json TEXT`** alongside it.
- `concept_edges` CHECK constraints are widened in the `DDL` (fresh DBs). Existing file DBs keep the
  old CHECK; they won't receive `similarity`/`digested` rows until recreated via seed/`reset_db`,
  which is how the demo and tests get their DBs — acceptable and additive.
- `papers.arxiv_id` already serves as the source id; we add `source_type` + `url` only.

---

## Task 1: Schema additions

**Files:**
- Modify: `litnav/storage/schema.py`
- Test: `tests/test_ow1_schema.py`

- [ ] **Step 1: Write the failing test.** Create `tests/test_ow1_schema.py`:

```python
import sqlite3
from litnav.storage.schema import init_db


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def test_new_columns_present():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert "bloom_level" in _cols(conn, "keypoints")
    assert {"distractors_json", "irt_b"} <= _cols(conn, "quiz_items")
    assert {"source_type", "url"} <= _cols(conn, "papers")
    assert "irt_theta" in _cols(conn, "learner_state")


def test_new_tables_present():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert {"learner_goal", "review_queue", "digest_cache"} <= _tables(conn)


def test_similarity_and_digested_edges_insertable():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1,'a','A'),(2,'b','B')")
    # both the new edge_type and the new source must satisfy the (widened) CHECK
    conn.execute("INSERT INTO concept_edges (prereq_concept, target_concept, edge_type, source) "
                 "VALUES (1,2,'similarity','digested')")
    row = conn.execute("SELECT edge_type, source FROM concept_edges").fetchone()
    assert row == ("similarity", "digested")


def test_existing_suite_unaffected_smoke():
    # init_db must still create the legacy tables used elsewhere
    conn = sqlite3.connect(":memory:"); init_db(conn)
    assert {"concepts", "concept_edges", "quiz_items", "learner_state", "cost_ledger"} <= _tables(conn)
```

- [ ] **Step 2: Run it, confirm failures.** `python -m pytest tests/test_ow1_schema.py -q`
  Expected: failures on the missing columns/tables and the CHECK rejecting `similarity`/`digested`.

- [ ] **Step 3: Widen the two `concept_edges` CHECKs in `DDL`.** In `litnav/storage/schema.py`,
  change the `concept_edges` table's two lines to:

```sql
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts','similarity')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced','digested')) DEFAULT 'curated',
```

- [ ] **Step 4: Add the new columns in `DDL`.**
  - In `keypoints`, change `sort_order INTEGER DEFAULT 0` to:
    ```sql
        sort_order INTEGER DEFAULT 0,
        bloom_level TEXT DEFAULT 'recall'
    ```
  - In `quiz_items`, change `targets_misconception TEXT` (the last column) to:
    ```sql
        targets_misconception TEXT,
        distractors_json TEXT,
        irt_b REAL
    ```
  - In `papers`, change `pdf_path TEXT` (last column) to:
    ```sql
        pdf_path TEXT,
        source_type TEXT,
        url TEXT
    ```
  - In `learner_state`, change `evidence TEXT,` to:
    ```sql
        evidence TEXT,
        irt_theta REAL,
    ```
    (keep the existing `updated_at` line and `PRIMARY KEY` after it).

- [ ] **Step 5: Add the three new tables to `DDL`** (append before the closing `"""`, after `cost_ledger`):

```sql
CREATE TABLE IF NOT EXISTS learner_goal (
    session_id TEXT REFERENCES sessions(id),
    goal_text TEXT,
    goal_type TEXT CHECK(goal_type IN ('mastery','functional','survey')) DEFAULT 'mastery',
    target_concepts_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id)
);

CREATE TABLE IF NOT EXISTS review_queue (
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    due_at TEXT,
    fsrs_state_json TEXT,
    PRIMARY KEY (session_id, concept_id)
);

CREATE TABLE IF NOT EXISTS digest_cache (
    slice_key TEXT PRIMARY KEY,
    status TEXT CHECK(status IN ('cached','building')) DEFAULT 'building',
    graph_version INTEGER DEFAULT 1,
    built_at TEXT,
    human_checked INTEGER DEFAULT 0
);
```

- [ ] **Step 6: Add idempotent ALTER migrations for existing file DBs.** In `init_db()`, extend the
  existing `for stmt in [ ... ]` list with:

```python
        "ALTER TABLE keypoints ADD COLUMN bloom_level TEXT DEFAULT 'recall'",
        "ALTER TABLE quiz_items ADD COLUMN distractors_json TEXT",
        "ALTER TABLE quiz_items ADD COLUMN irt_b REAL",
        "ALTER TABLE papers ADD COLUMN source_type TEXT",
        "ALTER TABLE papers ADD COLUMN url TEXT",
        "ALTER TABLE learner_state ADD COLUMN irt_theta REAL",
```

  (The three new tables need no ALTER — `executescript(DDL)` creates them. The widened
  `concept_edges` CHECK applies to fresh DBs only, as noted above.)

- [ ] **Step 7: Run the new tests + full suite.** `python -m pytest tests/test_ow1_schema.py -q`
  (expect 4 passed), then `python -m pytest -q` (no regressions).

- [ ] **Step 8: Commit.**
```bash
git add litnav/storage/schema.py tests/test_ow1_schema.py
git commit -m "feat(ow1): schema additions (similarity/digested edges, goal/review/digest tables, irt + provenance columns)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Repo writers for the new tables

**Files:**
- Create: `litnav/storage/openworld_repo.py`
- Test: `tests/test_openworld_repo.py`

- [ ] **Step 1: Write the failing test.** Create `tests/test_openworld_repo.py`:

```python
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import openworld_repo as ow


def _conn():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    conn.execute("INSERT INTO sessions (id, topic, status) VALUES ('s','t','active')")
    conn.execute("INSERT INTO concepts (id, slug, name) VALUES (1,'a','A'),(2,'b','B')")
    return conn


def test_learner_goal_set_get():
    conn = _conn()
    ow.set_goal(conn, "s", "learn A", "functional", [1, 2])
    g = ow.get_goal(conn, "s")
    assert g["goal_text"] == "learn A"
    assert g["goal_type"] == "functional"
    assert g["target_concepts"] == [1, 2]
    # upsert: a second set overwrites
    ow.set_goal(conn, "s", "learn A deeply", "mastery", [1])
    g2 = ow.get_goal(conn, "s")
    assert g2["goal_type"] == "mastery" and g2["target_concepts"] == [1]


def test_learner_goal_missing_is_none():
    assert ow.get_goal(_conn(), "nobody") is None


def test_review_queue_enqueue_and_due():
    conn = _conn()
    ow.enqueue_review(conn, "s", 1, due_at="2026-06-20T00:00:00", fsrs_state={"stability": 1.0})
    ow.enqueue_review(conn, "s", 2, due_at="2026-06-25T00:00:00", fsrs_state={"stability": 2.0})
    due = ow.due_reviews(conn, "s", now="2026-06-21T00:00:00")
    assert [d["concept_id"] for d in due] == [1]          # only the one already due
    assert due[0]["fsrs_state"] == {"stability": 1.0}
    # re-enqueue same concept updates in place (no duplicate)
    ow.enqueue_review(conn, "s", 1, due_at="2026-07-01T00:00:00", fsrs_state={"stability": 5.0})
    assert ow.due_reviews(conn, "s", now="2026-06-21T00:00:00") == []


def test_digest_cache_miss_then_hit():
    conn = _conn()
    assert ow.cache_get(conn, "linear-algebra::eigen") is None     # cold = miss
    ow.cache_put(conn, "linear-algebra::eigen", graph_version=1, human_checked=False)
    hit = ow.cache_get(conn, "linear-algebra::eigen")
    assert hit["status"] == "cached" and hit["graph_version"] == 1
```

- [ ] **Step 2: Run it, confirm `ModuleNotFoundError`.** `python -m pytest tests/test_openworld_repo.py -q`

- [ ] **Step 3: Implement `litnav/storage/openworld_repo.py`:**

```python
"""Repo writers for the open-world tables: learner_goal, review_queue, digest_cache."""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3


# ── learner_goal ──────────────────────────────────────────────────────────────
def set_goal(conn: sqlite3.Connection, session_id: str, goal_text: str, goal_type: str,
             target_concepts: list[int]) -> None:
    """Upsert the session's learning goal (one row per session)."""
    conn.execute(
        "INSERT INTO learner_goal (session_id, goal_text, goal_type, target_concepts_json) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "goal_text=excluded.goal_text, goal_type=excluded.goal_type, "
        "target_concepts_json=excluded.target_concepts_json",
        (session_id, goal_text, goal_type, json.dumps(target_concepts)),
    )
    conn.commit()


def get_goal(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute(
        "SELECT goal_text, goal_type, target_concepts_json FROM learner_goal WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return {"goal_text": row[0], "goal_type": row[1],
            "target_concepts": json.loads(row[2]) if row[2] else []}


# ── review_queue (FSRS spacing) ───────────────────────────────────────────────
def enqueue_review(conn: sqlite3.Connection, session_id: str, concept_id: int, *,
                   due_at: str, fsrs_state: dict) -> None:
    """Schedule (or reschedule) a concept's spaced review. One row per (session, concept)."""
    conn.execute(
        "INSERT INTO review_queue (session_id, concept_id, due_at, fsrs_state_json) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(session_id, concept_id) DO UPDATE SET "
        "due_at=excluded.due_at, fsrs_state_json=excluded.fsrs_state_json",
        (session_id, concept_id, due_at, json.dumps(fsrs_state)),
    )
    conn.commit()


def due_reviews(conn: sqlite3.Connection, session_id: str, now: str) -> list[dict]:
    """Concepts whose due_at <= now, oldest first."""
    rows = conn.execute(
        "SELECT concept_id, due_at, fsrs_state_json FROM review_queue "
        "WHERE session_id=? AND due_at<=? ORDER BY due_at",
        (session_id, now),
    ).fetchall()
    return [{"concept_id": r[0], "due_at": r[1],
             "fsrs_state": json.loads(r[2]) if r[2] else {}} for r in rows]


# ── digest_cache (demand-driven memoization; no prediction) ───────────────────
def cache_get(conn: sqlite3.Connection, slice_key: str) -> dict | None:
    row = conn.execute(
        "SELECT status, graph_version, built_at, human_checked FROM digest_cache WHERE slice_key=?",
        (slice_key,),
    ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "graph_version": row[1], "built_at": row[2],
            "human_checked": bool(row[3])}


def cache_put(conn: sqlite3.Connection, slice_key: str, *, graph_version: int = 1,
              human_checked: bool = False) -> None:
    """Mark a digested slice as cached. Upsert keyed by slice_key."""
    conn.execute(
        "INSERT INTO digest_cache (slice_key, status, graph_version, built_at, human_checked) "
        "VALUES (?, 'cached', ?, ?, ?) "
        "ON CONFLICT(slice_key) DO UPDATE SET "
        "status='cached', graph_version=excluded.graph_version, built_at=excluded.built_at, "
        "human_checked=excluded.human_checked",
        (slice_key, graph_version, _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
         1 if human_checked else 0),
    )
    conn.commit()
```

- [ ] **Step 4: Run the new tests + full suite.** `python -m pytest tests/test_openworld_repo.py -q`
  (expect 4 passed), then `python -m pytest -q` (no regressions).

- [ ] **Step 5: Commit.**
```bash
git add litnav/storage/openworld_repo.py tests/test_openworld_repo.py
git commit -m "feat(ow1): repo writers for learner_goal, review_queue, digest_cache" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review
- **Spec coverage (§4):** similarity edges + digested source (T1 Step 3); keypoints.bloom_level,
  quiz_items.distractors_json/irt_b, papers.source_type/url, learner_state.irt_theta (T1 Step 4);
  learner_goal, review_queue, digest_cache tables (T1 Step 5) + writers (T2). `cost_ledger` already
  landed in OW-0. ✓ Deviations noted (difficulty stays INTEGER; arxiv_id serves as source id).
- **Placeholders:** none — full DDL and code given.
- **Type consistency:** `set_goal/get_goal` ↔ `target_concepts` list; `enqueue_review/due_reviews`
  ↔ `fsrs_state` dict; `cache_get/cache_put` ↔ `{status, graph_version, ...}` — consistent across
  tasks and tests.
- **Out of scope (later milestones):** populating the new columns from nodes (OW-2/OW-4), seeding
  fixtures with similarity edges, IRT computation — OW-1 only readies the schema + new-table writers.
