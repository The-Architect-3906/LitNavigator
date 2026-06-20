import sqlite3
from litnav.storage.schema import init_db
from litnav.llm import result_cache as rc

def _emb(vecs):
    return lambda texts: [vecs]  # one query vector

def test_exact_hash_hit():
    c = sqlite3.connect(":memory:"); init_db(c)
    rc.store(c, "digest", "Extract concepts from X", {"concepts": [1]}, embedder=_emb([1.0, 0.0]))
    hit, res = rc.lookup(c, "digest", "extract   concepts from x", embedder=_emb([0.0, 1.0]))
    assert hit is True and res == {"concepts": [1]}   # normalized hash matches despite spacing/case

def test_semantic_hit_above_092():
    c = sqlite3.connect(":memory:"); init_db(c)
    rc.store(c, "digest", "prompt one", {"r": 1}, embedder=_emb([1.0, 0.0]))
    hit, res = rc.lookup(c, "digest", "a totally different prompt string", embedder=_emb([0.98, 0.20]))
    assert hit is True and res == {"r": 1}            # cosine([0.98,0.2],[1,0]) >= 0.92

def test_below_092_miss():
    c = sqlite3.connect(":memory:"); init_db(c)
    rc.store(c, "digest", "prompt one", {"r": 1}, embedder=_emb([1.0, 0.0]))
    hit, res = rc.lookup(c, "digest", "different", embedder=_emb([0.0, 1.0]))
    assert hit is False and res is None               # orthogonal -> miss

def test_stage_isolation():
    c = sqlite3.connect(":memory:"); init_db(c)
    rc.store(c, "digest", "p", {"r": 1}, embedder=_emb([1.0, 0.0]))
    hit, _ = rc.lookup(c, "digest_verify", "p", embedder=_emb([1.0, 0.0]))
    assert hit is False                               # different stage -> no hit
