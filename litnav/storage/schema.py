from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    level INTEGER DEFAULT 0,
    is_demo_core BOOLEAN DEFAULT 0,
    frontier_flag TEXT CHECK(frontier_flag IN ('consensus','contested','open'))
);

CREATE TABLE IF NOT EXISTS concept_edges (
    prereq_concept INTEGER REFERENCES concepts(id),
    target_concept INTEGER REFERENCES concepts(id),
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts','similarity')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced','digested')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence TEXT,
    PRIMARY KEY (prereq_concept, target_concept, edge_type)
);

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY,
    arxiv_id TEXT UNIQUE,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT,
    source_org TEXT,
    year INTEGER,
    full_text TEXT,
    pdf_path TEXT,
    source_type TEXT,
    url TEXT
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    concept_id INTEGER REFERENCES concepts(id),
    section TEXT,
    chunk_index INTEGER DEFAULT 0,
    text TEXT NOT NULL,
    token_count INTEGER,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS keypoints (
    id TEXT PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    name TEXT NOT NULL,
    objective TEXT,
    evidence_chunk_id TEXT REFERENCES paper_chunks(id),
    sort_order INTEGER DEFAULT 0,
    bloom_level TEXT DEFAULT 'recall'
);

CREATE TABLE IF NOT EXISTS quiz_items (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    keypoint_id TEXT REFERENCES keypoints(id),
    bloom_level TEXT DEFAULT 'recall',
    question TEXT NOT NULL,
    answer_key TEXT NOT NULL,
    qtype TEXT DEFAULT 'mcq',
    difficulty INTEGER DEFAULT 1,
    evidence_chunk_id TEXT REFERENCES paper_chunks(id),
    source_paper_id INTEGER REFERENCES papers(id),
    rubric TEXT,
    expected_keypoints TEXT,
    targets_misconception TEXT,
    distractors_json TEXT,
    irt_b REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learner_state (
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    mastery REAL NOT NULL,
    confidence REAL NOT NULL,
    n_observations INTEGER DEFAULT 0,
    held_misconceptions TEXT,
    tried_strategies TEXT,
    depth TEXT,
    evidence TEXT,
    irt_theta REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, concept_id)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
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

CREATE TABLE IF NOT EXISTS route_steps (
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

CREATE TABLE IF NOT EXISTS decisions (
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

CREATE TABLE IF NOT EXISTS misconceptions (
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

CREATE TABLE IF NOT EXISTS tutor_turns (
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

CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id TEXT PRIMARY KEY REFERENCES paper_chunks(id),
    dim INTEGER,
    vector TEXT,                  -- JSON list[float]
    model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS induction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    kind TEXT,                    -- 'prereq' | 'misconception'
    output TEXT,                  -- JSON of the induced element
    evidence_chunks TEXT,         -- JSON list of chunk ids
    confidence REAL,
    confidence_basis TEXT,        -- JSON: {n_chunks, max_strength, multi_paper}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS discover_results (
    query_key TEXT PRIMARY KEY,
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS result_cache (
    stage TEXT,
    input_hash TEXT,
    embedding TEXT,
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stage, input_hash)
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    # Idempotent migrations for existing file-based DBs
    for stmt in [
        "ALTER TABLE quiz_items ADD COLUMN keypoint_id TEXT",
        "ALTER TABLE quiz_items ADD COLUMN bloom_level TEXT DEFAULT 'recall'",
        "ALTER TABLE quiz_items ADD COLUMN rubric TEXT",
        "ALTER TABLE quiz_items ADD COLUMN expected_keypoints TEXT",
        "ALTER TABLE keypoints ADD COLUMN bloom_level TEXT DEFAULT 'recall'",
        "ALTER TABLE quiz_items ADD COLUMN distractors_json TEXT",
        "ALTER TABLE quiz_items ADD COLUMN irt_b REAL",
        "ALTER TABLE papers ADD COLUMN source_type TEXT",
        "ALTER TABLE papers ADD COLUMN url TEXT",
        "ALTER TABLE learner_state ADD COLUMN irt_theta REAL",
        "ALTER TABLE concepts ADD COLUMN source TEXT DEFAULT 'curated'",
        "ALTER TABLE concepts ADD COLUMN domain TEXT",
        "ALTER TABLE concepts ADD COLUMN slice_key TEXT",
        "ALTER TABLE concept_edges ADD COLUMN slice_key TEXT",
        "ALTER TABLE digest_cache ADD COLUMN model_key TEXT",
        "ALTER TABLE papers ADD COLUMN source_id TEXT",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass  # column already exists
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    """Drop all domain tables and recreate them, IN PLACE (no file unlink).

    Used by one-shot demos so a fresh run cannot hit a Windows PermissionError trying to
    delete a SQLite file the panel/server still has open."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (name,) in rows:
        conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.commit()
    init_db(conn)
