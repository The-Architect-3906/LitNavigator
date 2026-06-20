"""DIGEST stage 3 — verify high-impact prereq edges + compute the edge-accuracy spot-check.

A prereq edge survives as a hard 'prerequisite' only if its confidence >= VERIFY_THRESHOLD AND
(when high_impact) a FRONTIER judge agrees it is a genuine prerequisite. Otherwise it is downgraded
to a soft 'similarity' edge and flagged in unverified_edges (lit-review risk A: on-the-fly prereq
accuracy is untested, so edges are a soft constraint, never a hard gate). edge_accuracy() returns the
judge-agreement fraction surfaced in the Glass-box (OW-6).
"""
from __future__ import annotations

import sqlite3

from litnav.digest.contract import VERIFY_THRESHOLD
from litnav.llm import router


def _judge(edge: dict, judge_labels: dict, *, session_id, conn, budget) -> bool:
    """True if the prerequisite relation holds. Offline: read judge_labels. Live: frontier model."""
    key = f"{edge['prereq_slug']}->{edge['target_slug']}"
    prompt = (
        f"Is '{edge['prereq_slug']}' genuinely a prerequisite for understanding "
        f"'{edge['target_slug']}', based on the cited evidence chunks {edge['evidence']}? "
        'Respond as JSON: {"is_prerequisite": true|false}'
    )
    result = router.complete_json(prompt, tier="frontier", stage="digest_verify",
                                  fallback={"is_prerequisite": judge_labels.get(key, True)},
                                  session_id=session_id, conn=conn, budget=budget)
    val = result.get("is_prerequisite") if isinstance(result, dict) else None
    return bool(val) if isinstance(val, bool) else bool(judge_labels.get(key, True))


def verify_edges(edges: list[dict], *, judge_labels: dict, session_id: str | None,
                 conn: sqlite3.Connection | None, budget: int | None = None
                 ) -> tuple[list[dict], list[dict]]:
    """Gate prerequisite edges. Returns (all_edges_with_verified_flag, downgraded_edges):
    every edge gets a `verified` bool; low-confidence or judge-rejected prereq edges are
    downgraded to soft `similarity` edges and also collected into the second list."""
    out: list[dict] = []
    unverified: list[dict] = []
    for e in edges:
        e = dict(e)
        if e["edge_type"] != "prerequisite":
            e["verified"] = True                       # similarity edges are not gated
            out.append(e)
            continue
        ok = e["confidence"] >= VERIFY_THRESHOLD
        if ok and e.get("high_impact"):
            ok = _judge(e, judge_labels, session_id=session_id, conn=conn, budget=budget)
        if ok:
            e["verified"] = True
        else:
            e["edge_type"] = "similarity"              # downgrade: soft constraint, not a hard gate
            e["verified"] = False
            unverified.append(e)
        out.append(e)
    return out, unverified


def edge_accuracy(edges: list[dict], *, judge_labels: dict, session_id: str | None,
                  conn: sqlite3.Connection | None, budget: int | None = None,
                  sample_n: int = 10) -> float:
    """Fraction of (sampled) prereq edges a judge agrees are genuine prerequisites. 1.0 if none."""
    prereq = [e for e in edges if e["edge_type"] == "prerequisite"][:sample_n]
    if not prereq:
        return 1.0
    agreed = sum(1 for e in prereq
                 if _judge(e, judge_labels, session_id=session_id, conn=conn, budget=budget))
    return round(agreed / len(prereq), 4)
