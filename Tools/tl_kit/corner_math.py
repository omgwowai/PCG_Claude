"""corner_math.py -- pure-Python reference model of the corner and edge rules in
/Game/PCG/TL/PCG_TL_SplineBuilding
(docs/superpowers/specs/2026-10-09-tl-spline-building-design.md, section 4, and
docs/superpowers/plans/2026-10-12-tl-spline-building.md, rulings R1-R3).

Units are cm; coordinates are UE world XY treated as a plain 2D plane. A
footprint is the closed facade line as a list of (x, y) vertices, either
winding. The graph is checked against this model (acceptance A1-A6), so every
rule the graph applies to a corner or an edge is written here first.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common  # noqa: E402

COLLINEAR_DEG = 1.0        # |turn| below this: the vertex is dropped (CleanSpline)
SLICE_MAX_DEG = 10.0       # one fan slice covers at most this much turn
SLICE_HALF_DEG = 5.0       # the fan meshes are modelled as +-5 deg wedges
MAX_FAN_SLICES = 18        # template points per corner: ceil(180 / 10)
ACUTE_TURN_DEG = 90.0      # a convex corner turning more than this is acute


def level_rules(level):
    """Edge rules for one storey. pier_cm: end pier run (0 = no piers);
    filler_cm: the stretchable filler's native run; mid_grammar: the grammar
    for edges too short for F0 but long enough for two piers and a filler."""
    if level == 0:
        return {"pier_cm": 0.0, "filler_cm": 200.0, "filler": "FS2",
                "mid_grammar": "[FC][FS2]+[LC]", "foundation": True,
                "grammars": kit_common.level_grammars(0),
                "flengths": kit_common.level_flengths_cm(0)}
    return {"pier_cm": kit_common.END_PIER_CM, "filler_cm": 325.0, "filler": "WS1",
            "mid_grammar": "[FC][WS1][LC]", "foundation": False,
            "grammars": kit_common.level_grammars(level),
            "flengths": kit_common.level_flengths_cm(level)}


def signed_area(pts):
    """Shoelace area; > 0 when the vertices wind counter-clockwise with x to
    the right and y up."""
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def wrap(deg):
    """Wrap an angle to (-180, 180]."""
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def turn_deg(prev, cur, nxt):
    """Signed turn at `cur` from edge prev->cur to edge cur->nxt, degrees;
    > 0 is a left turn in the same convention as signed_area."""
    a_in = math.degrees(math.atan2(cur[1] - prev[1], cur[0] - prev[0]))
    a_out = math.degrees(math.atan2(nxt[1] - cur[1], nxt[0] - cur[0]))
    return wrap(a_out - a_in)


def clean(pts, collinear_deg=COLLINEAR_DEG):
    """Drop coincident vertices and vertices whose |turn| < collinear_deg,
    repeating until stable (what CleanSpline does with the same threshold)."""
    out = [tuple(map(float, p)) for p in pts]
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            prev, cur, nxt = out[i - 1], out[i], out[(i + 1) % len(out)]
            if (math.hypot(cur[0] - prev[0], cur[1] - prev[1]) < 1e-6
                    or abs(turn_deg(prev, cur, nxt)) < collinear_deg):
                del out[i]
                changed = True
                break
    return out


def classify(pts):
    """Per vertex: the signed turn, whether the corner is convex (it turns the
    same way the footprint winds) and whether it is acute (convex, interior
    angle < 90 deg)."""
    s = 1.0 if signed_area(pts) > 0 else -1.0
    res = []
    for i in range(len(pts)):
        t = turn_deg(pts[i - 1], pts[i], pts[(i + 1) % len(pts)])
        convex = t * s > 0
        res.append({"turn": t, "convex": convex,
                    "acute": convex and abs(t) > ACUTE_TURN_DEG})
    return res


def exterior_normal_deg(p0, p1, area_sign):
    """Direction (deg) of the exterior normal of edge p0->p1: right of travel
    for a counter-clockwise footprint, left of travel for a clockwise one."""
    a = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    return wrap(a - 90.0 * area_sign)


def fan(pts, i):
    """The fan slices at vertex i: one dict per slice with its centre direction
    `yaw` (deg, world; the slice mesh's local +X), the half angle `a`, the mesh
    scales `sx`, `sy`, and `kind` ('front' at a convex corner, 'back' at a
    concave one). The slices sweep from the incoming edge's exterior normal to
    the outgoing edge's; the slice mesh's pivot is the vertex."""
    s = 1.0 if signed_area(pts) > 0 else -1.0
    prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
    na = exterior_normal_deg(prev, cur, s)
    nb = exterior_normal_deg(cur, nxt, s)
    sweep = wrap(nb - na)
    if abs(sweep) < COLLINEAR_DEG:
        return []
    n = max(1, math.ceil(abs(sweep) / SLICE_MAX_DEG - 1e-9))
    a = abs(sweep) / (2.0 * n)
    sx = math.cos(math.radians(a)) / math.cos(math.radians(SLICE_HALF_DEG))
    sy = math.sin(math.radians(a)) / math.sin(math.radians(SLICE_HALF_DEG))
    kind = "front" if classify(pts)[i]["convex"] else "back"
    return [{"k": k, "yaw": wrap(na + sweep * (k + 0.5) / n), "a": a,
             "sx": sx, "sy": sy, "kind": kind} for k in range(n)]


def edge_plan(pts, i, level):
    """The edge from vertex i to i+1 on one storey: its length and either the
    grammar the graph writes for it or, for an edge too short for two piers
    and a filler, one stretched filler (`short`, with its run scale)."""
    r = level_rules(level)
    p0, p1 = pts[i], pts[(i + 1) % len(pts)]
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    short_cm = r["filler_cm"] + 2.0 * r["pier_cm"]
    if length < short_cm:
        return {"length": length, "short": True, "symbol": r["filler"],
                "scale": length / r["filler_cm"], "grammar": None}
    fl = r["flengths"]
    if length >= fl[2]:
        g = r["grammars"][2]
    elif length >= fl[1]:
        g = r["grammars"][1]
    elif length >= fl[0]:
        g = r["grammars"][0]
    else:
        g = r["mid_grammar"]
    if r["foundation"]:
        g = g.replace("[FC]", "").replace("[LC]", "")
    else:
        cls = classify(pts)
        g = g.replace("[FC", "[EAL" if cls[i]["acute"] else "[EL")
        g = g.replace("[LC", "[EAR" if cls[(i + 1) % len(pts)]["acute"] else "[ER")
    return {"length": length, "short": False, "symbol": None, "scale": 1.0, "grammar": g}
