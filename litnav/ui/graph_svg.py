"""Render a concept_graph() dict as a self-contained inline SVG.

No dependency, no JS, fully offline — the project runs without network, so the graph must too.
Layered left-to-right layout (prereqs on the left). Fill encodes learner state, the outline
encodes frontier status, induced nodes/edges are dashed. Returned string is embedded directly
in the Jinja templates (use the |safe filter).
"""
from __future__ import annotations

import html

# Learner-state fill colors — dark-surface-safe, consistent with the B1 design system.
# Surfaces: --s1 #181d27, --s2 #1f2636, --s3 #28334a
_STATE_FILL = {
    "idle":     "#1f2636",   # --s2: neutral dark, unvisited
    "current":  "#28334a",   # --s3: slightly brighter, active concept
    "mastered": "#172b20",   # --ok (#2da65c) tinted surface: mastered
    "conceded": "#2b1f10",   # --warn (#b3700d) tinted surface: conceded
    "lectured": "#1e2638",   # --accent (#E0A33C) tinted surface: lectured/oriented
}
# Frontier outline colors — semantic status tokens from B1.
_FRONTIER_STROKE = {"consensus": "#2da65c", "contested": "#b3700d", "open": "#b3700d"}
_CURRENT_STROKE = "#E0A33C"   # --accent amber: active concept border

_COL_W, _ROW_H = 215, 66
_NODE_W, _NODE_H = 158, 42
_PAD_X, _PAD_Y = 16, 16


def _layers(nodes: list[dict], edges: list[dict]) -> dict[int, int]:
    """Longest-path layering: a node sits one column right of its deepest prerequisite."""
    ids = {n["id"] for n in nodes}
    preds: dict[int, list[int]] = {i: [] for i in ids}
    for e in edges:
        if e["target_id"] in ids and e["prereq_id"] in ids:
            preds[e["target_id"]].append(e["prereq_id"])
    layer: dict[int, int] = {}

    def depth(i: int, seen: frozenset = frozenset()) -> int:
        if i in layer:
            return layer[i]
        if not preds[i] or i in seen:
            layer[i] = 0
            return 0
        layer[i] = 1 + max(depth(p, seen | {i}) for p in preds[i])
        return layer[i]

    for i in ids:
        depth(i)
    return layer


def to_svg(graph: dict, *, max_label: int = 20) -> str:
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    if not nodes:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'></svg>"

    layer = _layers(nodes, edges)
    # Order rows within a column by node id for stable layout.
    by_col: dict[int, list[dict]] = {}
    for n in sorted(nodes, key=lambda d: d["id"]):
        by_col.setdefault(layer[n["id"]], []).append(n)

    pos: dict[int, tuple[float, float]] = {}
    for col, col_nodes in by_col.items():
        for row, n in enumerate(col_nodes):
            x = _PAD_X + col * _COL_W
            y = _PAD_Y + row * _ROW_H
            pos[n["id"]] = (x, y)

    n_cols = max(by_col) + 1
    n_rows = max(len(v) for v in by_col.values())
    width = _PAD_X * 2 + (n_cols - 1) * _COL_W + _NODE_W
    height = _PAD_Y * 2 + (n_rows - 1) * _ROW_H + _NODE_H

    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' "
        f"width='100%' style='max-width:{width}px;font-family:system-ui,sans-serif'>",
        "<defs><marker id='arw' markerWidth='8' markerHeight='8' refX='7' refY='3' "
        "orient='auto'><path d='M0,0 L7,3 L0,6 z' fill='#4a5568'/></marker></defs>",
    ]

    # Edges first (under nodes). Right edge of prereq -> left edge of target.
    for e in edges:
        if e["prereq_id"] not in pos or e["target_id"] not in pos:
            continue
        x1, y1 = pos[e["prereq_id"]]
        x2, y2 = pos[e["target_id"]]
        sx, sy = x1 + _NODE_W, y1 + _NODE_H / 2
        tx, ty = x2, y2 + _NODE_H / 2
        dash = " stroke-dasharray='4 3'" if e["source"] == "induced" else ""
        parts.append(
            f"<path d='M{sx:.0f},{sy:.0f} C{sx + 40:.0f},{sy:.0f} {tx - 40:.0f},{ty:.0f} "
            f"{tx:.0f},{ty:.0f}' fill='none' stroke='#4a5568' stroke-width='1.5'"
            f"{dash} marker-end='url(#arw)'/>"
        )

    # Nodes.
    for n in nodes:
        x, y = pos[n["id"]]
        fill = _STATE_FILL.get(n["state"], _STATE_FILL["idle"])
        if n["state"] == "current":
            stroke, sw = _CURRENT_STROKE, 3
        else:
            stroke, sw = _FRONTIER_STROKE.get(n["frontier_flag"], "#4a5568"), 1.5
        dash = " stroke-dasharray='5 3'" if n["induced"] else ""
        label = n["name"] if len(n["name"]) <= max_label else n["name"][: max_label - 1] + "…"
        parts.append(
            f"<g><rect x='{x:.0f}' y='{y:.0f}' rx='8' width='{_NODE_W}' height='{_NODE_H}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{dash}/>"
            f"<text x='{x + _NODE_W / 2:.0f}' y='{y + _NODE_H / 2 + 4:.0f}' text-anchor='middle' "
            f"font-size='12' fill='#e2e8f0'>{html.escape(label)}</text></g>"
        )

    parts.append("</svg>")
    return "".join(parts)
