"""Stop-condition for the autonomous eval-gated improvement loop.

The loop keeps applying backlog items while the headline keeps climbing; it stops when the gain
flattens (last `plateau_n` deltas each below `eps`) or the iteration `cap` is hit.
"""
from __future__ import annotations


def should_stop(curve: list[float], *, eps: float = 0.01, cap: int = 10, plateau_n: int = 2) -> tuple[bool, str]:
    """curve = weighted-headline per recorded scorecard (oldest→newest)."""
    if len(curve) >= cap:
        return True, f"iteration cap reached ({len(curve)} ≥ {cap})"
    if len(curve) > plateau_n:
        deltas = [curve[i] - curve[i - 1] for i in range(1, len(curve))]
        if all(d < eps for d in deltas[-plateau_n:]):
            return True, f"plateau: last {plateau_n} gains < {eps}"
    return False, "still improving"
