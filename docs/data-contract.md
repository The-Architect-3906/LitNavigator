# Data Contract

This document defines the data shape shared by the state machine, storage layer, seed fixtures, evaluation scripts, and demo UI.

## Storage Principle

SQLite is the source of durable demo truth. Runtime state may live in memory or a LangGraph checkpoint, but anything the judge should inspect must be written into domain tables.

## M0 Seed Fixture

M0 uses `data/seed/rag_demo.json`.

Required shape:

```json
{
  "topic": "RAG for scientific QA",
  "targets": ["dense_retrieval", "contrastive_learning", "rag_pipeline", "evaluation"],
  "concepts": [
    {
      "id": 1,
      "slug": "dense_retrieval",
      "name": "Dense retrieval",
      "frontier_flag": "consensus"
    }
  ],
  "edges": [
    {
      "prereq_concept": 1,
      "target_concept": 4,
      "edge_type": "prerequisite",
      "source": "curated",
      "confidence": 1.0
    }
  ],
  "papers": [
    {
      "id": 1,
      "title": "Dense Retrieval for Scientific Question Answering",
      "year": 2023
    }
  ],
  "chunks": [
    {
      "id": "c_dense_1",
      "paper_id": 1,
      "concept_id": 1,
      "text": "Dense retrieval represents queries and documents in an embedding space."
    }
  ],
  "quiz_items": [
    {
      "id": 1,
      "concept_id": 1,
      "question": "Dense retrieval mainly compares documents using what representation?",
      "answer_key": "embedding vectors",
      "evidence_chunk_id": "c_dense_1",
      "source_paper_id": 1
    }
  ]
}
```

`targets` lists the concepts the **planner** sequences into the initial route. Prerequisites that are *not* in `targets` (e.g. `negative_sampling`) are assumed mastered and only inserted by `replan` when a quiz reveals a gap — this is what enables the M1 reroute money shot. The fixture must include an `evaluation` concept so the demo route `Dense → Contrastive → RAG → Evaluation` matches the data, and `negative_sampling` as a prereq edge into `contrastive_learning` that is **not** a target.

LLM usage by milestone: **M0/M1 require no LLM** (no embeddings, no LLM calls, no live paper APIs). **M2 `grade` (misconception detection) and M3 `induce_scaffold` call an LLM when `LITNAV_LLM_PROVIDER=qwen`, and fall back to deterministic fixtures when `none`** — so all gates pass fully offline. Scope note: M2 grade genuinely lets the LLM pick the misconception id (validated against candidates); **M3 induce currently only lets the LLM label evidence *strength*** — the induced edge/misconception structure comes from the offline candidate. Fully autonomous M3 extraction is future work (see `docs/evaluation.md`).

## Core Tables

### `concepts`

```sql
CREATE TABLE concepts (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    level INTEGER DEFAULT 0,
    is_demo_core BOOLEAN DEFAULT 0,
    frontier_flag TEXT CHECK(frontier_flag IN ('consensus','contested','open'))
);
```

### `concept_edges`

```sql
CREATE TABLE concept_edges (
    prereq_concept INTEGER REFERENCES concepts(id),
    target_concept INTEGER REFERENCES concepts(id),
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence TEXT,
    PRIMARY KEY (prereq_concept, target_concept, edge_type)
);
```

### `papers`

```sql
CREATE TABLE papers (
    id INTEGER PRIMARY KEY,
    arxiv_id TEXT UNIQUE,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT,
    source_org TEXT,
    year INTEGER,
    full_text TEXT,
    pdf_path TEXT
);
```

### `paper_chunks`

```sql
CREATE TABLE paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    concept_id INTEGER REFERENCES concepts(id),
    section TEXT,
    chunk_index INTEGER DEFAULT 0,
    text TEXT NOT NULL,
    token_count INTEGER,
    embedding_id TEXT
);
```

### `quiz_items`

```sql
CREATE TABLE quiz_items (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    question TEXT NOT NULL,
    answer_key TEXT NOT NULL,
    qtype TEXT DEFAULT 'mcq',
    difficulty INTEGER DEFAULT 1,
    evidence_chunk_id TEXT REFERENCES paper_chunks(id),
    source_paper_id INTEGER REFERENCES papers(id),
    rubric TEXT,
    expected_concepts TEXT,
    targets_misconception TEXT
);
```

### `sessions`

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `learner_state`

```sql
CREATE TABLE learner_state (
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    mastery REAL NOT NULL,
    confidence REAL NOT NULL,
    n_observations INTEGER DEFAULT 0,
    held_misconceptions TEXT,
    tried_strategies TEXT,
    depth TEXT,
    evidence TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, concept_id)
);
```

### `quiz_attempts`

```sql
CREATE TABLE quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    quiz_item_id INTEGER REFERENCES quiz_items(id),
    user_answer TEXT,
    score REAL,
    feedback TEXT,
    concept_score_delta TEXT,
    detected_misconception TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `route_steps`

```sql
CREATE TABLE route_steps (
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER,
    step_id TEXT,
    concept_id INTEGER REFERENCES concepts(id),
    paper_id INTEGER REFERENCES papers(id),
    status TEXT,
    reason TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, route_version, step_id)
);
```

### `decisions`

```sql
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER,
    from_node TEXT,
    decision TEXT,
    rationale TEXT,
    state_snapshot TEXT,
    token_cost INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## M2 Tables

### `misconceptions`

```sql
CREATE TABLE misconceptions (
    id TEXT PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    wrong_model TEXT,
    correct_model TEXT,
    detect_hint TEXT,
    reteach_strategy TEXT,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence_chunk_id TEXT REFERENCES paper_chunks(id)
);
```

### `tutor_turns`

```sql
CREATE TABLE tutor_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    turn_type TEXT,
    strategy TEXT,
    pre_check_score REAL,
    post_check_score REAL,
    mastery_after REAL,
    confidence_after REAL,
    cited_chunks TEXT,
    token_cost INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## M3 Tables

### `induction_log`

```sql
CREATE TABLE induction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    kind TEXT,
    output TEXT,
    evidence_chunks TEXT,
    confidence REAL,
    confidence_basis TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Runtime State Fields

`ConceptState`:

```python
{
    "mastery": 0.4,
    "confidence": 0.0,
    "n_observations": 0,
    "evidence": [],
    "held_misconceptions": [],
    "tried_strategies": [],
    "depth": "recall"
}
```

`RouteStep`:

```python
{
    "step_id": "route-001",
    "concept_id": 1,
    "paper_id": 1,
    "reason": "This concept unlocks the next route step.",
    "status": "pending",
    "confidence": 1.0
}
```

## Confidence Rules

Learner-state confidence is separate from mastery:

```python
confidence = 1 - 0.6 ** n_observations
```

Induced-scaffold confidence is computed from evidence. This is the **single canonical formula** — it must stay byte-identical here, in `litnavigator-build-spec.md` §5.3, and in the engineering plan's induce task:

```python
def induced_confidence(n_chunks, max_strength, multi_paper):
    # max_strength ∈ {'weak_hint','general_statement','explicit_assertion'}
    strength_bonus = {"weak_hint": 0.05, "general_statement": 0.15, "explicit_assertion": 0.25}[max_strength]
    multi_paper_bonus = 0.10 if multi_paper else 0.0
    return round(min(0.95, 0.35 + 0.15 * n_chunks + strength_bonus + multi_paper_bonus), 2)
```

Worked example: `1 chunk + explicit_assertion + single paper → 0.75`. The number is always deterministic, inspectable, and computed from evidence — never an LLM-generated float.

## Data Deferrals

Do not add these before the milestone that needs them:

- citations: M3/M4,
- Chroma embedding ids: M1+ optional,
- full PDF paths: M2+ optional,
- cross-session learner memory: M4,
- user auth tables: after competition demo.
