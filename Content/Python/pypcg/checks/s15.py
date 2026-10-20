"""V1 checks of stage 15, MainTowerVisuals (spec 3, V1).

The main node reads the terrain (`MeshTerrain`, a surface), so its record cannot be replayed whole (trap 60:
`replayed: 0`). `check_record` replays what the record CAN rebuild -- every step that needs no terrain: the
align, the outer ring, the three arm sectors, the hexagons on the recorded inner ring, the tree samples and the
plaza's xy -- with the editor's own booleans, and compares them with the recorded outputs; then the invariants,
each from this module's own reading of the geometry:

  - empty inputs -> no outputs and no exceptions (every one of the six Python nodes);
  - the tree ring lies on the ring area: every tree point is inside the input shape at 500 cm from its
    boundary (the `ContractTreeRing` band), `int(L / 1000)` of them;
  - the rings nest instead of overlapping the arms: each contracted ring (`s15_tower_level1..3`) lies inside
    the rooftop it was made from, within the contract distance of it, and no hexagon overlaps another. (The
    brief's "the rings do not overlap the arms" does not hold for the official tower in plan: measured on the
    slim geometry, which matches the taps to 1e-11 cm, each arm sector overlaps the 32.5 m inner ring by
    1013.6 of its 1089.2 m2 and the other arms by 99.1 m2 -- the arms rise through the CHC block. So the check
    pins what the official graph does guarantee: stacked rings inside the tower below them.)
  - the three arm sectors are one sector turned: equal areas and equal sorted edge lengths;
  - the hexagons sit on the inner ring's vertices; the plaza tiles lie inside the input shape.

`TOL_CM` is geometry noise only (no threshold here is a randomness allowance: the stage's only draws are the
tree kit and scale, which no clause reads).
"""
import json
import math
import os

from pypcg import geo
from pypcg.geo import Points, Polygon, Spline

TOL_CM = 0.01
TREE_BAND_CM = 500.0               # ContractTreeRing, this module's own copy
TREE_SPACING_CM = 1000.0
CONTRACT_CM = {"OuterChj": 400.0, "Chj2": 400.0, "Skyscraper": 1000.0, "Arm90": 150.0, "Arm80": 150.0, "Arm70": 150.0}
LEVELS = (("s15_level1", {"OuterChj": "ChcRoofs", "Arm90": "Arm90Roofs", "Arm80": "Arm80Roofs", "Arm70": "Arm70Roofs"}),
          ("s15_level2", {"Chj2": "Chj1Roofs", "Arm90": "Arm90Roofs", "Arm80": "Arm80Roofs", "Arm70": "Arm70Roofs"}),
          ("s15_level3", {"Skyscraper": "Chj2Roofs", "Arm90": "Arm90Roofs", "Arm80": "Arm80Roofs", "Arm70": "Arm70Roofs"}))


# ---- this module's own geometry ------------------------------------------------------------------------
def ring_of(v):
    if isinstance(v, Spline):
        return [tuple(p[:2]) for p in v.points]
    if isinstance(v, Polygon):
        return [tuple(p[:2]) for p in v.outer]
    return []


def area(r):
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2.0


def dist_to_ring(p, r):
    best = float("inf")
    for i in range(len(r)):
        a, b = r[i], r[(i + 1) % len(r)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def inside(p, r):
    return geo.inside(p, r) or dist_to_ring(p, r) <= TOL_CM


def edges(r):
    return sorted(round(math.dist(r[i], r[(i + 1) % len(r)]), 3) for i in range(len(r)))


def convex_overlap(a, b):
    """The overlap area of two convex rings (Sutherland-Hodgman), cm2."""
    def ccw(r):
        s = sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))
        return list(r) if s > 0 else list(r)[::-1]
    out, clip = ccw(a), ccw(b)
    for i in range(len(clip)):
        p, q = clip[i], clip[(i + 1) % len(clip)]
        side = lambda x: (q[0] - p[0]) * (x[1] - p[1]) - (q[1] - p[1]) * (x[0] - p[0])
        cur, out = out, []
        for j in range(len(cur)):
            s, e = cur[j], cur[(j + 1) % len(cur)]
            if side(s) >= 0:
                out.append(s)
            if (side(s) >= 0) != (side(e) >= 0):
                t = side(s) / (side(s) - side(e))
                out.append((s[0] + t * (e[0] - s[0]), s[1] + t * (e[1] - s[1])))
        if len(out) < 3:
            return 0.0
    return area(out)


def _values(items):
    return [v for v, _t in items]


# ---- the invariants ------------------------------------------------------------------------------------
def check(inputs, params, outputs, ops, official=None):
    """The main node's invariants on one record's outputs (`inputs` may be None: not replayable)."""
    fails = []
    shape = []
    for v in _values((inputs or {}).get("Volume", [])):
        shape = ring_of(v) or shape
    busy = [pin for pin, items in outputs.items() if items]
    if inputs is not None and not shape:
        return ["no input shape but outputs on %s" % busy] if busy else []
    if not shape:
        return fails

    # the tree ring lies on the ring area
    for pin in ("TreeBases", "Trees"):
        pts = [p for v in _values(outputs.get(pin, [])) if isinstance(v, Points) for p in v.loc]
        if not pts:
            continue
        band = [p for p in pts if not (inside(p[:2], shape) and abs(dist_to_ring(p[:2], shape) - TREE_BAND_CM) <= TOL_CM)]
        if band:
            fails.append("%s: %d of %d points off the 500 cm band inside the input shape (first %s, %.3f cm in)"
                         % (pin, len(band), len(pts), tuple(round(c, 1) for c in band[0][:2]),
                            dist_to_ring(band[0][:2], shape)))
        n = len(shape)
        inner_len = sum(math.dist(shape[i], shape[(i + 1) % n]) for i in range(n)) - 2 * n * TREE_BAND_CM * math.tan(
            math.pi / n) if n >= 3 else 0.0
        if n == 6 and len(pts) != int(inner_len / TREE_SPACING_CM):
            fails.append("%s: %d points, want int(%.3f / %g) = %d" % (pin, len(pts), inner_len, TREE_SPACING_CM,
                                                                     int(inner_len / TREE_SPACING_CM)))

    # the three arm sectors are one sector turned
    secs = [ring_of(v) for pin in ("Sector90", "Sector80", "Sector70") for v in _values(outputs.get(pin, []))]
    if len(secs) == 3:
        if max(area(s) for s in secs) - min(area(s) for s in secs) > 1.0:
            fails.append("arm sectors of unequal area %s m2" % [round(area(s) / 1e4, 3) for s in secs])
        if any(max(abs(a - b) for a, b in zip(edges(s), edges(secs[0]))) > TOL_CM for s in secs[1:]):
            fails.append("arm sectors are not one shape: edges %s" % [edges(s) for s in secs])

    # the hexagons: on the inner ring's vertices, mutually disjoint
    inner = [ring_of(v) for v in _values(outputs.get("InnerRing", []))]
    hexes = [ring_of(v) for v in _values(outputs.get("Hexagons", []))]
    if inner and hexes:
        for k, h in enumerate(hexes):
            c = (sum(p[0] for p in h) / len(h), sum(p[1] for p in h) / len(h))
            if min(math.dist(c, q) for q in inner[0]) > TOL_CM:
                fails.append("hexagon %d centred %.3f cm off every inner-ring vertex" % (k, min(math.dist(c, q) for q in inner[0])))
        for i in range(len(hexes)):
            for j in range(i + 1, len(hexes)):
                if convex_overlap(hexes[i], hexes[j]) > 1.0:
                    fails.append("hexagons %d and %d overlap by %.1f cm2" % (i, j, convex_overlap(hexes[i], hexes[j])))

    # the plaza inside the input shape
    tiles = [p for v in _values(outputs.get("PlazaTiles", [])) if isinstance(v, Points) for p in v.loc]
    out = [p for p in tiles if not inside(p[:2], shape)]
    if out:
        fails.append("%d plaza tiles outside the input shape" % len(out))
    return fails


def check_levels(runs_dir):
    """The level nodes' last records: every contracted ring inside the rooftop it came from, within the
    contract distance of it (the rings nest; s15.md 8-9)."""
    fails = []
    for name, pins in LEVELS:
        path = os.path.join(runs_dir, name + ".json")
        if not os.path.exists(path):
            fails.append("no %s record" % name)
            continue
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        for out_pin, in_pin in pins.items():
            roofs = [ring_of(geo.from_json(v)) for v, _t in rec["inputs"].get(in_pin, [])]
            for v, _t in rec["outputs"].get(out_pin, []):
                r = ring_of(geo.from_json(v))
                owner = next((q for q in roofs if all(inside(p, q) for p in r)), None)
                if owner is None:
                    fails.append("%s.%s: a ring outside every %s rooftop" % (name, out_pin, in_pin))
                    continue
                near = min(dist_to_ring(p, owner) for p in r)
                if near < CONTRACT_CM[out_pin] - TOL_CM:
                    fails.append("%s.%s: a vertex %.3f cm from its rooftop, want >= %g" % (name, out_pin, near,
                                                                                          CONTRACT_CM[out_pin]))
    return fails


def replay(rec, ops):
    """The terrain-free part of the main node, replayed with `ops` from the record's own inputs, against the
    recorded outputs: the arm sectors and the hexagons (on the recorded inner ring) vertex for vertex, the
    tree sample count and the plaza tile count."""
    from pypcg.stages import s15_main_tower_visuals as S
    inputs = {}
    for pin in ("Volume",):
        try:
            inputs[pin] = [(geo.from_json(v), frozenset(t)) for v, t in rec["inputs"].get(pin, [])]
        except ValueError:
            return ["%s: not readable from the record" % pin]
    shape = S.shape_of(inputs)
    if not shape:
        return []
    fails = []
    outer = S.outer_ring(S.aligned(shape), ops)
    secs = S.arms(outer, shape, S.pivot_of(inputs), ops)
    for pin in ("Sector90", "Sector80", "Sector70"):
        got = [ring_of(geo.from_json(v)) for v, _t in rec["outputs"].get(pin, [])]
        want = [tuple(p[:2]) for p in secs[pin]]
        if len(got) != 1 or len(got[0]) != len(want) or max(math.dist(a, b) for a, b in zip(got[0], want)) > 1e-6:
            fails.append("replay: %s differs from the recorded ring" % pin)
    inner = [geo.from_json(v) for v, _t in rec["outputs"].get("InnerRing", [])]
    if inner:
        want = S.hexagons([tuple(p) for p in inner[0].points])
        got = [ring_of(geo.from_json(v)) for v, _t in rec["outputs"].get("Hexagons", [])]
        if len(got) != len(want) or any(max(math.dist(a, b[:2]) for a, b in zip(g, w)) > 1e-6 for g, w in zip(got, want)):
            fails.append("replay: the hexagons differ from the recorded ones")
    samples, _z = S.tree_samples(shape, ops)
    trees = sum(v.get("n", 0) for v, _t in rec["outputs"].get("Trees", []))
    if rec["outputs"].get("Trees") and trees != len(samples):
        fails.append("replay: %d tree samples, %d trees recorded" % (len(samples), trees))
    tiles = sum(v.get("n", 0) for v, _t in rec["outputs"].get("PlazaTiles", []))
    locs, _yaw = geo.ground.fill_uniform([(p[0], p[1]) for p in shape], shape[0][2], S.PLAZA_EXTENT_CM)
    if tiles != len(locs):
        fails.append("replay: %d plaza tiles, %d recorded" % (len(locs), tiles))
    return fails


def check_record(rec, ops, official=None):
    """V1's entry: the partial replay, the main node's invariants on the record, the level nodes' nesting."""
    from pypcg import stage_api
    fails = replay(rec, ops)
    try:
        inputs = {pin: [(geo.from_json(v), frozenset(t)) for v, t in items] for pin, items in rec["inputs"].items()
                  if pin != "MeshTerrain"}
    except ValueError:
        inputs = None
    outputs = {}
    for pin, items in rec["outputs"].items():
        try:
            outputs[pin] = [(geo.from_json(v), t) for v, t in items]
        except ValueError:
            continue                                   # a truncated (summary-only) point set
    fails += check(inputs, {}, outputs, ops, official)
    fails += check_levels(stage_api.RUNS_DIR)
    return fails[:40]
