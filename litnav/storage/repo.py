from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def create_session(conn: sqlite3.Connection, session_id: str, topic: str, user_id: str = "demo") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, user_id, topic, status) VALUES (?,?,?,?)",
        (session_id, user_id, topic, "active"),
    )
    conn.commit()


def upsert_learner_state(
    conn: sqlite3.Connection,
    session_id: str,
    concept_id: int,
    mastery: float,
    confidence: float,
    n_observations: int,
    held_misconceptions: list[str] | None = None,
    tried_strategies: list[str] | None = None,
    depth: str = "recall",
    evidence: list | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO learner_state
            (session_id, concept_id, mastery, confidence, n_observations,
             held_misconceptions, tried_strategies, depth, evidence, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(session_id, concept_id) DO UPDATE SET
            mastery=excluded.mastery,
            confidence=excluded.confidence,
            n_observations=excluded.n_observations,
            held_misconceptions=excluded.held_misconceptions,
            tried_strategies=excluded.tried_strategies,
            depth=excluded.depth,
            evidence=excluded.evidence,
            updated_at=excluded.updated_at
        """,
        (
            session_id, concept_id, mastery, confidence, n_observations,
            json.dumps(held_misconceptions or []),
            json.dumps(tried_strategies or []),
            depth,
            json.dumps(evidence or []),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def write_route_steps(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    steps: list[dict],
) -> None:
    for step in steps:
        conn.execute(
            """
            INSERT OR IGNORE INTO route_steps
                (session_id, route_version, step_id, concept_id, paper_id, status, reason, confidence)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                session_id, route_version, step["step_id"], step["concept_id"],
                step.get("paper_id"), step.get("status", "pending"),
                step.get("reason", ""), step.get("confidence", 1.0),
            ),
        )
    conn.commit()


def update_route_step_status(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    step_id: str,
    status: str,
) -> None:
    conn.execute(
        "UPDATE route_steps SET status=? WHERE session_id=? AND route_version=? AND step_id=?",
        (status, session_id, route_version, step_id),
    )
    conn.commit()


def record_quiz_attempt(
    conn: sqlite3.Connection,
    session_id: str,
    quiz_item_id: int,
    user_answer: str,
    score: float,
    feedback: str,
    concept_score_delta: dict | None = None,
    detected_misconception: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO quiz_attempts
            (session_id, quiz_item_id, user_answer, score, feedback, concept_score_delta, detected_misconception)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            session_id, quiz_item_id, user_answer, score, feedback,
            json.dumps(concept_score_delta or {}),
            detected_misconception,
        ),
    )
    conn.commit()


def record_decision(
    conn: sqlite3.Connection,
    session_id: str,
    route_version: int,
    from_node: str,
    decision: str,
    rationale: str,
    state_snapshot: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO decisions
            (session_id, route_version, from_node, decision, rationale, state_snapshot)
        VALUES (?,?,?,?,?,?)
        """,
        (
            session_id, route_version, from_node, decision, rationale,
            json.dumps(state_snapshot or {}),
        ),
    )
    conn.commit()


def get_quiz_item(conn: sqlite3.Connection, concept_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, concept_id, question, answer_key, evidence_chunk_id, source_paper_id "
        "FROM quiz_items WHERE concept_id=? LIMIT 1",
        (concept_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "concept_id": row[1], "question": row[2],
        "answer_key": row[3], "evidence_chunk_id": row[4], "source_paper_id": row[5],
    }


def get_concept_prereqs(conn: sqlite3.Connection, concept_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT prereq_concept FROM concept_edges WHERE target_concept=? AND edge_type='prerequisite'",
        (concept_id,),
    ).fetchall()
    return [r[0] for r in rows]


def get_learner_mastery(conn: sqlite3.Connection, session_id: str, concept_id: int) -> float | None:
    row = conn.execute(
        "SELECT mastery FROM learner_state WHERE session_id=? AND concept_id=?",
        (session_id, concept_id),
    ).fetchone()
    return row[0] if row else None


def get_parallel_quiz_items(
    conn: sqlite3.Connection, concept_id: int, exclude_ids: list[int] | None = None
) -> list[dict]:
    """Return quiz items for a concept (ordered by id). Used for pre/post parallel forms:
    the caller excludes already-used item ids so pre and post draw different forms."""
    rows = conn.execute(
        "SELECT id, concept_id, question, answer_key, qtype, difficulty, "
        "evidence_chunk_id, source_paper_id, targets_misconception "
        "FROM quiz_items WHERE concept_id=? ORDER BY id",
        (concept_id,),
    ).fetchall()
    items = [
        {"id": r[0], "concept_id": r[1], "question": r[2], "answer_key": r[3],
         "qtype": r[4], "difficulty": r[5], "evidence_chunk_id": r[6],
         "source_paper_id": r[7], "targets_misconception": r[8]}
        for r in rows
    ]
    exclude = set(exclude_ids or [])
    fresh = [it for it in items if it["id"] not in exclude]
    return fresh if fresh else items  # fall back to reusing when all forms used


def get_misconceptions_for_concept(conn: sqlite3.Connection, concept_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, concept_id, wrong_model, correct_model, detect_hint, reteach_strategy, "
        "source, confidence, evidence_chunk_id FROM misconceptions WHERE concept_id=?",
        (concept_id,),
    ).fetchall()
    return [
        {"id": r[0], "concept_id": r[1], "wrong_model": r[2], "correct_model": r[3],
         "detect_hint": r[4], "reteach_strategy": r[5], "source": r[6],
         "confidence": r[7], "evidence_chunk_id": r[8]}
        for r in rows
    ]


def record_tutor_turn(
    conn: sqlite3.Connection,
    session_id: str,
    concept_id: int,
    turn_type: str,
    strategy: str,
    pre_check_score: float | None,
    post_check_score: float | None,
    cited_chunks: list[str] | None = None,
    token_cost: int = 0,
    mastery_after: float | None = None,
    confidence_after: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO tutor_turns
            (session_id, concept_id, turn_type, strategy, pre_check_score, post_check_score,
             mastery_after, confidence_after, cited_chunks, token_cost)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (session_id, concept_id, turn_type, strategy, pre_check_score, post_check_score,
         mastery_after, confidence_after, json.dumps(cited_chunks or []), token_cost),
    )
    conn.commit()


def get_last_tutor_post_score(
    conn: sqlite3.Connection, session_id: str, concept_id: int
) -> float | None:
    row = conn.execute(
        "SELECT post_check_score FROM tutor_turns "
        "WHERE session_id=? AND concept_id=? ORDER BY id DESC LIMIT 1",
        (session_id, concept_id),
    ).fetchone()
    return row[0] if row else None


# ── M3: literature-induced scaffolding writers ──────────────────────────────

def get_concept_by_slug(conn: sqlite3.Connection, slug: str) -> dict | None:
    row = conn.execute(
        "SELECT id, slug, name, frontier_flag, source, domain FROM concepts WHERE slug=?", (slug,)
    ).fetchone()
    return {"id": row[0], "slug": row[1], "name": row[2], "frontier_flag": row[3],
            "source": row[4], "domain": row[5]} if row else None


def next_concept_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM concepts").fetchone()
    return int(row[0]) + 1


# Allowed by the concepts.frontier_flag CHECK constraint. Anything else (e.g. an LLM emitting
# 'established'/'novel') must be coerced to NULL — otherwise INSERT OR IGNORE silently DROPS the
# whole concept row on the CHECK violation, leaving the graph empty (the OW-5.1 persistence bug).
_FRONTIER_FLAGS = {"consensus", "contested", "open"}


def create_concept(conn: sqlite3.Connection, concept_id: int, slug: str, name: str,
                   frontier_flag: str | None = None, *, source: str = "curated",
                   domain: str | None = None, slice_key: str | None = None) -> None:
    if frontier_flag not in _FRONTIER_FLAGS:
        frontier_flag = None
    conn.execute(
        "INSERT OR IGNORE INTO concepts (id, slug, name, frontier_flag, source, domain, slice_key) "
        "VALUES (?,?,?,?,?,?,?)",
        (concept_id, slug, name, frontier_flag, source, domain, slice_key),
    )
    conn.commit()


def record_edge(conn: sqlite3.Connection, prereq_concept: int, target_concept: int, *,
                edge_type: str, source: str, confidence: float,
                evidence_chunks: list[str], slice_key: str | None = None) -> None:
    """Generic typed edge writer. edge_type in {prerequisite, similarity, ...}; source in
    {curated, induced, digested}. Idempotent on (prereq, target, edge_type)."""
    conn.execute(
        "INSERT OR IGNORE INTO concept_edges "
        "(prereq_concept, target_concept, edge_type, source, confidence, evidence, slice_key) "
        "VALUES (?,?,?,?,?,?,?)",
        (prereq_concept, target_concept, edge_type, source, confidence,
         json.dumps(evidence_chunks), slice_key),
    )
    conn.commit()


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
    edges = [{"prereq_slug": id_to_slug.get(r[0]), "target_slug": id_to_slug.get(r[1]),
              "edge_type": r[2], "confidence": r[3],
              "evidence": json.loads(r[4]) if r[4] else []} for r in erows]
    return {"concepts": concepts, "edges": edges}


def record_induced_edge(conn: sqlite3.Connection, prereq_concept: int, target_concept: int,
                        confidence: float, evidence_chunks: list[str]) -> None:
    record_edge(conn, prereq_concept, target_concept, edge_type="prerequisite",
                source="induced", confidence=confidence, evidence_chunks=evidence_chunks)


def get_concept_edges(conn: sqlite3.Connection, source: str | None = None) -> list[dict]:
    """All edges, optionally filtered by source. evidence is decoded from JSON."""
    sql = ("SELECT prereq_concept, target_concept, edge_type, source, confidence, evidence "
           "FROM concept_edges")
    params: tuple[str, ...] = ()
    if source is not None:
        sql += " WHERE source=?"
        params = (source,)
    rows = conn.execute(sql, params).fetchall()
    return [{"prereq_concept": r[0], "target_concept": r[1], "edge_type": r[2],
             "source": r[3], "confidence": r[4],
             "evidence": json.loads(r[5]) if r[5] else []} for r in rows]


def create_keypoint(conn: sqlite3.Connection, kp_id: str, concept_id: int, name: str,
                    objective: str, evidence_chunk_id: str | None = None,
                    sort_order: int = 0, bloom_level: str = "recall") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO keypoints "
        "(id, concept_id, name, objective, evidence_chunk_id, sort_order, bloom_level) "
        "VALUES (?,?,?,?,?,?,?)",
        (kp_id, concept_id, name, objective, evidence_chunk_id, sort_order, bloom_level),
    )
    conn.commit()


def record_induced_misconception(conn: sqlite3.Connection, mid: str, concept_id: int,
                                 wrong_model: str, correct_model: str, confidence: float,
                                 evidence_chunk_id: str | None, detect_hint: str | None = None,
                                 reteach_strategy: str = "analogy") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO misconceptions "
        "(id, concept_id, wrong_model, correct_model, detect_hint, reteach_strategy, "
        " source, confidence, evidence_chunk_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (mid, concept_id, wrong_model, correct_model, detect_hint, reteach_strategy,
         "induced", confidence, evidence_chunk_id),
    )
    conn.commit()


def record_induction_log(conn: sqlite3.Connection, session_id: str, kind: str, output: dict,
                         evidence_chunks: list[str], confidence: float,
                         confidence_basis: dict) -> None:
    conn.execute(
        "INSERT INTO induction_log "
        "(session_id, kind, output, evidence_chunks, confidence, confidence_basis) "
        "VALUES (?,?,?,?,?,?)",
        (session_id, kind, json.dumps(output), json.dumps(evidence_chunks),
         confidence, json.dumps(confidence_basis)),
    )
    conn.commit()


def assign_chunk_concept(conn: sqlite3.Connection, chunk_id: str, concept_id: int) -> None:
    """Tag an ingested chunk to a concept so retrieve_node (which filters by concept_id)
    can serve it. Used when an induced concept adopts its supporting evidence."""
    conn.execute("UPDATE paper_chunks SET concept_id=? WHERE id=?", (concept_id, chunk_id))
    conn.commit()


def create_quiz_item(conn: sqlite3.Connection, concept_id: int, question: str, answer_key: str,
                     evidence_chunk_id: str | None = None, source_paper_id: int | None = None,
                     qtype: str = "explain", difficulty: int = 1,
                     targets_misconception: str | None = None,
                     rubric: str | None = None,
                     expected_keypoints: str | None = None,
                     keypoint_id: str | None = None,
                     bloom_level: str = "recall",
                     distractors_json: str | None = None,
                     irt_b: float | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO quiz_items "
        "(concept_id, keypoint_id, bloom_level, question, answer_key, qtype, difficulty, "
        " evidence_chunk_id, source_paper_id, rubric, expected_keypoints, targets_misconception, "
        " distractors_json, irt_b) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (concept_id, keypoint_id, bloom_level, question, answer_key, qtype, difficulty,
         evidence_chunk_id, source_paper_id, rubric, expected_keypoints, targets_misconception,
         distractors_json, irt_b),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_chunk_paper_id(conn: sqlite3.Connection, chunk_id: str) -> int | None:
    row = conn.execute("SELECT paper_id FROM paper_chunks WHERE id=?", (chunk_id,)).fetchone()
    return row[0] if row else None


def create_paper(conn: sqlite3.Connection, *, source_id: str | None = None,
                 arxiv_id: str | None = None, title: str,
                 source_type: str | None = None, url: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO papers (arxiv_id, title, source_type, url, source_id) VALUES (?,?,?,?,?)",
        (arxiv_id, title, source_type, url, source_id),
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


def get_induced_edges(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT prereq_concept, target_concept, confidence, evidence FROM concept_edges "
        "WHERE source='induced'"
    ).fetchall()
    return [{"prereq_concept": r[0], "target_concept": r[1], "confidence": r[2],
             "evidence": json.loads(r[3]) if r[3] else []} for r in rows]


def get_induction_log(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT kind, output, evidence_chunks, confidence, confidence_basis "
        "FROM induction_log WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()
    return [{"kind": r[0], "output": json.loads(r[1]) if r[1] else {},
             "evidence_chunks": json.loads(r[2]) if r[2] else [],
             "confidence": r[3], "confidence_basis": json.loads(r[4]) if r[4] else {}}
            for r in rows]


# ── Chunk embedding vectors (M4 vector retrieval) ──────────────────────────────

def save_chunk_vector(conn: sqlite3.Connection, chunk_id: str, vector: list[float],
                      model: str) -> None:
    conn.execute(
        "INSERT INTO chunk_vectors (chunk_id, dim, vector, model) VALUES (?,?,?,?) "
        "ON CONFLICT(chunk_id) DO UPDATE SET dim=excluded.dim, vector=excluded.vector, "
        "model=excluded.model",
        (chunk_id, len(vector), json.dumps(vector), model),
    )
    conn.commit()


def get_chunk_vectors(conn: sqlite3.Connection) -> list[dict]:
    """All stored chunk vectors joined with their text/paper for ranking."""
    rows = conn.execute(
        "SELECT v.chunk_id, v.vector, c.text, c.paper_id, c.concept_id "
        "FROM chunk_vectors v JOIN paper_chunks c ON c.id = v.chunk_id"
    ).fetchall()
    return [{"chunk_id": r[0], "vector": json.loads(r[1]), "text": r[2],
             "paper_id": r[3], "concept_id": r[4]} for r in rows]


def count_chunk_vectors(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]


# ── Keypoint / TEACH-ASSESS helpers ─────────────────────────────────────────

def get_keypoints(conn: sqlite3.Connection, concept_id: int) -> list[dict]:
    """Return keypoints for a concept in sort_order. Empty list if none seeded."""
    rows = conn.execute(
        "SELECT id, concept_id, name, objective, evidence_chunk_id, sort_order, bloom_level "
        "FROM keypoints WHERE concept_id=? ORDER BY sort_order",
        (concept_id,),
    ).fetchall()
    return [
        {"id": r[0], "concept_id": r[1], "name": r[2],
         "objective": r[3], "evidence_chunk_id": r[4], "sort_order": r[5],
         "bloom_level": r[6]}
        for r in rows
    ]


def get_chunk_text(conn: sqlite3.Connection, chunk_id: str) -> str:
    """Return raw text of a paper chunk (empty string if not found)."""
    row = conn.execute(
        "SELECT text FROM paper_chunks WHERE id=?", (chunk_id,)
    ).fetchone()
    return row[0] if row else ""


def get_quiz_by_kp_bloom(
    conn: sqlite3.Connection,
    keypoint_id: str,
    bloom_level: str,
    exclude_ids: list[int] | None = None,
) -> dict | None:
    """Return one quiz item for a keypoint at the given bloom level, skipping used ids."""
    exclude = set(exclude_ids or [])
    rows = conn.execute(
        "SELECT id, concept_id, keypoint_id, bloom_level, question, answer_key, "
        "qtype, difficulty, evidence_chunk_id, source_paper_id, rubric, "
        "expected_keypoints, targets_misconception "
        "FROM quiz_items WHERE keypoint_id=? AND bloom_level=? ORDER BY id",
        (keypoint_id, bloom_level),
    ).fetchall()
    for r in rows:
        if r[0] not in exclude:
            return {
                "id": r[0], "concept_id": r[1], "keypoint_id": r[2],
                "bloom_level": r[3], "question": r[4], "answer_key": r[5],
                "qtype": r[6], "difficulty": r[7], "evidence_chunk_id": r[8],
                "source_paper_id": r[9], "rubric": r[10],
                "expected_keypoints": r[11], "targets_misconception": r[12],
            }
    return None


def get_any_quiz_for_kp(
    conn: sqlite3.Connection,
    keypoint_id: str,
    exclude_ids: list[int] | None = None,
) -> dict | None:
    """Return any cached quiz for a keypoint, regardless of bloom level (preferring the lowest
    bloom). Digested quiz seeds may be stored at a bloom outside the assess ladder
    (recall/comprehension/application) — without a bloom-agnostic fallback they are unreachable
    and the concept always concedes. Skips used ids."""
    exclude = set(exclude_ids or [])
    _ORDER = {"recall": 0, "comprehension": 1, "application": 2}
    rows = conn.execute(
        "SELECT id, concept_id, keypoint_id, bloom_level, question, answer_key, "
        "qtype, difficulty, evidence_chunk_id, source_paper_id, rubric, "
        "expected_keypoints, targets_misconception "
        "FROM quiz_items WHERE keypoint_id=? ORDER BY id",
        (keypoint_id,),
    ).fetchall()
    rows = [r for r in rows if r[0] not in exclude]
    rows.sort(key=lambda r: _ORDER.get(r[3], 1))   # prefer lower bloom rung
    for r in rows:
        return {
            "id": r[0], "concept_id": r[1], "keypoint_id": r[2],
            "bloom_level": r[3], "question": r[4], "answer_key": r[5],
            "qtype": r[6], "difficulty": r[7], "evidence_chunk_id": r[8],
            "source_paper_id": r[9], "rubric": r[10],
            "expected_keypoints": r[11], "targets_misconception": r[12],
        }
    return None
