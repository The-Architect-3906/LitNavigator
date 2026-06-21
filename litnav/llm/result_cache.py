"""Semantic result cache (spec §5): exact (stage, normalized-hash) hit first, else embedding
cosine>=0.92 within the same stage. Caller injects an `embedder` (router passes client.embed_texts);
offline (embedder returns None) only the exact-hash layer works."""
from __future__ import annotations
import hashlib, json, math, sqlite3

COSINE_MIN = 0.92


def normalized_hash(prompt: str) -> str:
    return hashlib.sha1(" ".join(prompt.split()).lower().encode("utf-8")).hexdigest()[:16]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def lookup(conn: sqlite3.Connection, stage: str, prompt: str, *, embedder):
    h = normalized_hash(prompt)
    row = conn.execute("SELECT result_json FROM result_cache WHERE stage=? AND input_hash=?",
                       (stage, h)).fetchone()
    if row:
        return True, json.loads(row[0])
    vecs = embedder([prompt]) if embedder else None
    if not vecs:
        return False, None
    qv = vecs[0]
    for emb_json, result_json in conn.execute(
            "SELECT embedding, result_json FROM result_cache WHERE stage=?", (stage,)):
        if emb_json and _cosine(qv, json.loads(emb_json)) >= COSINE_MIN:
            return True, json.loads(result_json)
    return False, None


def store(conn: sqlite3.Connection, stage: str, prompt: str, result, *, embedder) -> None:
    h = normalized_hash(prompt)
    vecs = embedder([prompt]) if embedder else None
    emb_json = json.dumps(vecs[0]) if vecs else None
    conn.execute("INSERT OR REPLACE INTO result_cache (stage, input_hash, embedding, result_json) "
                 "VALUES (?,?,?,?)", (stage, h, emb_json, json.dumps(result)))
    conn.commit()
