"""Append-only eval-history + improvement curve.

Each loop iteration appends one Scorecard as a JSON line; `curve` re-derives the weighted headline
per entry so the improvement trajectory is visible at a glance.
"""
from __future__ import annotations

import json

from litnav.eval.scorecard import Scorecard, weighted_headline


def append(path: str, sc: Scorecard) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(sc.as_dict(), ensure_ascii=True) + "\n")


def load(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


def curve(path: str) -> list[float]:
    return [weighted_headline(Scorecard(**row)) for row in load(path)]
