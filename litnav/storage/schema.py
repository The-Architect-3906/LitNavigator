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
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
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
    pdf_path TEXT
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

CREATE TABLE IF NOT EXISTS quiz_items (
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
    cited_chunks TEXT,
    token_cost INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()
