"""Render a concept_graph() dict as a self-contained inline SVG.

No dependency, no JS, fully offline — the project runs without network, so the graph must too.
Layered left-to-right layout (prereqs on the left). Fill encodes learner state, the outline
encodes frontier status, induced nodes/edges are dashed. Returned string is embedded directly
in the Jinja templates (use the |safe filter).
"""
from __future__ import annotations

import html

# Learner-STATE drives the visible color (fill, border, text) — light "manuscript" palette matching
# the tutor map legend (current=amber, mastered=green, contested=red, idle=gray dashed). State is the
# signal; frontier_flag is only a secondary marker (contested override, below). The old code let
# frontier_flag paint every node's border green ("consensus") regardless of state, so the whole map
# looked mastered. Tuple = (fill, border, text).
_STATE_STYLE = {
    "idle":     ("#ffffff", "#d3cab8", "#9a907d"),   # not started — pale, dashed border
    "current":  ("#fff7ea", "#e08a1e", "#7a4d09"),   # active — amber fill + border
    "mastered": ("#f0faf3", "#4cae74", "#1f4d33"),   # mastered — green fill + border
    "conceded": ("#fdf1ef", "#ef6a4a", "#9e3318"),   # conceded / not-yet — red-ish
    "lectured": ("#eef1f6", "#9bb0cf", "#37445c"),   # oriented / lectured — cool blue-gray
}
_CONTESTED_BORDER = "#ef6a4a"      # surfaces a contested frontier on an otherwise-neutral node
_EDGE_STROKE = "#b3a98f"           # warm prerequisite edge
_INDUCED_EDGE_STROKE = "#c79a3f"   # dashed amber for induced/inferred edges
_SIMILARITY_STROKE = "#cfc7b5"     # pale dotted "related" link (undirected, not a prerequisite)

_COL_W, _ROW_H = 215, 66
_NODE_W, _NODE_H = 158, 42
_PAD_X, _PAD_Y = 16, 16


def _layers(nodes: list[dict], edges: list[dict]) -> dict[int, int]:
    """Longest-path layering: a node sits one column right of its deepest prerequisite."""
    ids = {n["id"] for n in nodes}
    preds: dict[int, list[int]] = {i: [] for i in ids}
    for e in edges:
        if e.get("kind") == "similarity":
            continue   # similarity is undirected, not a precedence relation — ignore for layering
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

    # Edges first (under nodes). Similarity ("related") links draw first, underneath: a pale dotted
    # straight line between node centers, undirected (no arrow). Prerequisites then draw on top as a
    # warm bezier from the prereq's right edge to the target's left edge, with a direction arrow.
    for e in edges:
        if e.get("kind") != "similarity":
            continue
        if e["prereq_id"] not in pos or e["target_id"] not in pos:
            continue
        ax, ay = pos[e["prereq_id"]]
        bx, by = pos[e["target_id"]]
        cx1, cy1 = ax + _NODE_W / 2, ay + _NODE_H / 2
        cx2, cy2 = bx + _NODE_W / 2, by + _NODE_H / 2
        parts.append(
            f"<line x1='{cx1:.0f}' y1='{cy1:.0f}' x2='{cx2:.0f}' y2='{cy2:.0f}' "
            f"stroke='{_SIMILARITY_STROKE}' stroke-width='1' stroke-dasharray='2 4'/>"
        )
    for e in edges:
        if e.get("kind") == "similarity":
            continue
        if e["prereq_id"] not in pos or e["target_id"] not in pos:
            continue
        x1, y1 = pos[e["prereq_id"]]
        x2, y2 = pos[e["target_id"]]
        sx, sy = x1 + _NODE_W, y1 + _NODE_H / 2
        tx, ty = x2, y2 + _NODE_H / 2
        induced = e["source"] == "induced"
        estroke = _INDUCED_EDGE_STROKE if induced else _EDGE_STROKE
        dash = " stroke-dasharray='4 3'" if induced else ""
        parts.append(
            f"<path d='M{sx:.0f},{sy:.0f} C{sx + 40:.0f},{sy:.0f} {tx - 40:.0f},{ty:.0f} "
            f"{tx:.0f},{ty:.0f}' fill='none' stroke='{estroke}' stroke-width='1.5'"
            f"{dash} marker-end='url(#arw)'/>"
        )

    # Nodes — STATE drives fill/border/text; current gets a thicker border; a contested frontier
    # overrides the border on neutral (idle/lectured) nodes; idle + induced nodes are dashed.
    for n in nodes:
        x, y = pos[n["id"]]
        state = n.get("state") or "idle"
        fill, stroke, text = _STATE_STYLE.get(state, _STATE_STYLE["idle"])
        sw = 2.5 if state == "current" else 1.5
        if state in ("idle", "lectured") and n.get("frontier_flag") == "contested":
            stroke = _CONTESTED_BORDER
        dash = " stroke-dasharray='5 3'" if (n.get("induced") or state == "idle") else ""
        label = n["name"] if len(n["name"]) <= max_label else n["name"][: max_label - 1] + "…"
        parts.append(
            f"<g><rect x='{x:.0f}' y='{y:.0f}' rx='8' width='{_NODE_W}' height='{_NODE_H}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{dash}/>"
            f"<text x='{x + _NODE_W / 2:.0f}' y='{y + _NODE_H / 2 + 4:.0f}' text-anchor='middle' "
            f"font-size='12' fill='{text}'>{html.escape(label)}</text></g>"
        )

    parts.append("</svg>")
    return "".join(parts)
