"""V1 checks of stage 16, CentralParkVisuals (spec 3, V1).

The recorded run is the VEGETATION node's (`s16_central_park_visuals`, record `s16`, one per V2 seed); its inputs
hold the Final terrain, so V1 cannot replay it (`replayed` 0, trap 60) and calls `check_record`: a partial replay
with the editor's booleans of what the record can rebuild -- the grown road footprints and the forest areas,
which the split must partition -- then the invariants on the recorded outputs. The GEOMETRY node's record
(`s16_geometry`, one file: the node is deterministic) is checked too when it is on disk.

Invariants (s16.md section 6 states the corrected ones):
  - the split: Selected and Unselected together are exactly the forest areas, each once;
  - no tree stands deeper than the fill's jitter reach (`PositionRange` 200 x sqrt 2 = 283 cm, plus 1 cm) inside
    the forest exclusion, a lake, the Met or a grown road footprint, and every tree is within that reach of a
    forest area of its own side; trees stand upright (roll and pitch 0) and carry one of their side's assets;
  - the Met rooftop handed to the rooftop assemblies is the building's, 10 cm lower;
  - geometry: each lake's water plane encloses its lake spline's polygon area within 1 %; the Met footprint is
    inside the park; every walkpath point is inside the contracted park pieces (1 cm for the split ends);
  - no park areas -> no trees and no split.
"""
import math

from pypcg import geo
from pypcg.geo import curves as C

JITTER_REACH_CM = 200.0 * math.sqrt(2.0) + 1.0
LAKE_AREA_TOL = 0.01
EDGE_TOL_CM = 1.0
AREA_KEY = 3                           # m2 rounded to this many decimals when matching area sets


def _values(items, kind=None):
    out = []
    for v, _t in items or []:
        if kind is None or isinstance(v, kind):
            out.append(v)
    return out


def ring_of(v):
    if isinstance(v, geo.Polygon):
        return [tuple(p[:2]) for p in v.outer]
    if isinstance(v, geo.Spline):
        return [tuple(p[:2]) for p in geo.drop_closing(list(v.polyline or v.points))]
    return []


def _bbox(ring, pad=0.0):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0.0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def depth_inside(p, poly):
    """How far `p` is inside `poly` (outer less holes), in cm: 0 when outside or on it."""
    rings = [poly.outer] + list(poly.holes)
    if not geo.inside(p, poly.outer) or any(geo.inside(p, h) for h in poly.holes):
        return 0.0
    return min(_seg_dist(p, r[k], r[(k + 1) % len(r)]) for r in rings for k in range(len(r)))


def dist_outside(p, poly):
    """How far `p` is outside `poly`, in cm: 0 when inside."""
    if geo.inside(p, poly.outer) and not any(geo.inside(p, h) for h in poly.holes):
        return 0.0
    rings = [poly.outer] + list(poly.holes)
    return min(_seg_dist(p, r[k], r[(k + 1) % len(r)]) for r in rings for k in range(len(r)))


class _Index:
    """Polygons by bounding box, padded, for point queries."""

    def __init__(self, polys, pad=0.0):
        self.items = [(p, _bbox(p.outer, pad)) for p in polys if len(p.outer) >= 3]

    def near(self, p):
        return [poly for poly, b in self.items if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]]


def _area_keys(polys):
    return sorted(round(geo.area_m2(p), AREA_KEY) for p in polys)


AREA_MATCH_M2 = 0.01                   # two area lists match when sorted pairwise within this (frame last bits)


def _same_areas(a, b):
    ka, kb = _area_keys(a), _area_keys(b)
    return len(ka) == len(kb) and all(abs(x - y) <= AREA_MATCH_M2 for x, y in zip(ka, kb))


def official_road_expand():
    """`Expand_Border_Footprint`'s `Expand` as the OFFICIAL IR stores it (800; its title says 425)."""
    from pypcg import dsl
    return float(dsl.official_node(16, "Expand_Border_Footprint")["overrides"]["Expand"])


def official_roof_drop():
    """`Subgraph_54`'s Z offset as the official IR stores it (-10)."""
    from pypcg import dsl
    return float(dsl.official_node(16, "Subgraph_54")["overrides"]["offset"]["Z"])


# ---- the vegetation record ---------------------------------------------------------------------------------
def check(inputs, params, outputs, ops, official=None):
    from pypcg.stages import s16_central_park_visuals as S
    f = []
    sel = _values(outputs.get("Selected"), geo.Polygon)
    uns = _values(outputs.get("Unselected"), geo.Polygon)
    trees = [(v, t) for v, t in outputs.get("Trees", []) if isinstance(v, geo.Points)]
    areas = S._polygons(inputs, "ParkAreas") if inputs is not None else None
    if areas is not None and not areas:
        if sel or uns or trees:
            f.append("no park areas, yet %d selected / %d unselected areas and %d tree items" % (len(sel), len(uns), len(trees)))
        return f
    clips, forest = [], None
    if inputs is not None:
        clips = S._polygons(inputs, "Exclusions")
    if inputs is not None and ops is not None:
        # Rebuilt HERE, not with the stage's own helpers: the growth comes from the official IR's override
        # (`Expand_Border_Footprint` Expand), the booleans straight from `ops` -- so a wrong constant or a dropped
        # clip set in the stage shows as a partition failure.
        roads = []
        for p in S._polygons(inputs, "RoadFootprints"):
            roads += ops.offset([p.outer] + list(p.holes), official_road_expand())
        excl = list(clips)
        clips = excl + roads
        forest = []
        cut = [r for c in clips for r in [c.outer] + list(c.holes)]
        for a in areas:
            forest += ops.difference([a.outer] + list(a.holes), cut) if cut else [a]
        if not _same_areas(forest, sel + uns):
            f.append("the split does not partition the forest areas: %d forest areas (%.1f m2), %d + %d split (%.1f m2)"
                     % (len(forest), sum(geo.area_m2(p) for p in forest), len(sel), len(uns),
                        sum(geo.area_m2(p) for p in sel + uns)))
    mega = bool((params or {}).get("UseMegaplantsTrees", False))
    f += _check_trees(trees, {"Selected": sel, "Unselected": uns}, clips, mega)
    if inputs is not None:
        roofs = [v for v, _t in inputs.get("MetRoofs", []) if isinstance(v, geo.Spline)]
        low = _values(outputs.get("MetRoofsLowered"), geo.Spline)
        if len(roofs) != len(low):
            f.append("%d Met rooftops in, %d lowered out" % (len(roofs), len(low)))
        for a, b in zip(roofs, low):
            if len(a.points) != len(b.points) or any(
                    p[0] != q[0] or p[1] != q[1] or abs((p[2] + official_roof_drop()) - q[2]) > 1e-9
                    for p, q in zip(a.points, b.points)):
                f.append("a lowered Met rooftop is not its rooftop 10 cm lower")
    return f


def _check_trees(trees, sides, clips, mega):
    from pypcg.stages import s16_central_park_visuals as S
    f = []
    if not trees:
        return f
    deep = _Index(clips)
    homes = {side: _Index(polys, JITTER_REACH_CM) for side, polys in sides.items()}
    bad_tilt = bad_asset = too_deep = homeless = 0
    worst = 0.0
    for pts, tags in trees:
        side = next((t for t in tags if t in sides), None)
        allowed = set(S.MEGA_TREES[side] if mega else S.FIELD_TREES) if side else set()
        assets = pts.attrs.get("Asset") or [None] * len(pts)
        for i, loc in enumerate(pts.loc):
            r = pts.rot[i]
            if abs(r[0]) > 1e-6 or abs(r[2]) > 1e-6:
                bad_tilt += 1
            if side and assets[i] not in allowed:
                bad_asset += 1
            p = (loc[0], loc[1])
            d = max([depth_inside(p, c) for c in deep.near(p)] or [0.0])
            worst = max(worst, d)
            if d > JITTER_REACH_CM:
                too_deep += 1
            if side and not any(dist_outside(p, a) <= JITTER_REACH_CM for a in homes[side].near(p)):
                homeless += 1
    if too_deep:
        f.append("%d trees stand deeper than %.0f cm inside an exclusion / lake / Met / road footprint (deepest %.1f cm)"
                 % (too_deep, JITTER_REACH_CM, worst))
    if homeless:
        f.append("%d trees are farther than %.0f cm from every forest area of their side" % (homeless, JITTER_REACH_CM))
    if bad_tilt:
        f.append("%d trees are not upright (roll / pitch not 0)" % bad_tilt)
    if bad_asset:
        f.append("%d trees carry an asset outside their side's kit list" % bad_asset)
    return f


# ---- the geometry record -----------------------------------------------------------------------------------
def curve_area_m2(spline, steps=64):
    """The area a closed curved spline encloses, from a dense evaluation of its Hermite segments (the mesh
    `Create_Mesh_Planar` triangulates is the spline's own polyline at 1 cm error)."""
    pts, tans = spline.points, spline.tangents or [(t, t) for t in C.auto_tangents(spline.points, True)]
    ring = []
    for s in range(len(pts)):
        for m in range(steps):
            q = C.position_at(pts, tans, True, s + m / float(steps))
            ring.append((q[0], q[1]))
    return abs(geo.signed_area(ring)) / 1e4


def check_geometry(rec, ops=None):
    """The geometry node's invariants on its record (no replay: the lakes and the Met need the terrain)."""
    f = []
    try:
        ins = {pin: [geo.from_json(v) for v, _t in items] for pin, items in rec["inputs"].items() if pin != "MeshTerrain"}
        outs = {pin: [geo.from_json(v) for v, _t in items] for pin, items in rec["outputs"].items()}
    except ValueError:
        return ["the geometry record cannot be read"]
    feet = [v for v in ins.get("Footprint", []) if isinstance(v, geo.Spline) and v.closed]
    if not feet:
        if any(outs.get(p) for p in outs):
            f.append("no park footprint, yet the geometry node has outputs")
        return f
    park = geo.Polygon(geo.ccw(ring_of(feet[0])), [], 0.0)
    lakes = [v for v in ins.get("Lake", []) if isinstance(v, geo.Spline) and v.closed]
    water = [v for v in outs.get("Lake", []) if isinstance(v, geo.Spline)]
    if len(lakes) != len(water):
        f.append("%d lakes in, %d water planes out" % (len(lakes), len(water)))
    for lk, w in zip(lakes, water):
        want = abs(geo.signed_area(ring_of(lk))) / 1e4
        got = curve_area_m2(w)
        if want > 0 and abs(got - want) > LAKE_AREA_TOL * want:
            f.append("a lake's water plane encloses %.1f m2, its spline's polygon %.1f m2 (over 1 %%)" % (got, want))
    for m in [v for v in outs.get("MetFootprint", []) if isinstance(v, geo.Spline)]:
        if any(not geo.inside(p[:2], park.outer) for p in m.points):
            f.append("the Met footprint is not inside the park")
    corners = [v for v in outs.get("Corners", []) if isinstance(v, geo.Polygon)]
    if corners:
        for w in [v for v in outs.get("Walkpaths", []) if isinstance(v, geo.Spline)]:
            for p in w.points:
                if not any(geo.inside(p[:2], c.outer) or dist_outside(p[:2], c) <= EDGE_TOL_CM for c in corners):
                    f.append("a walkpath point %s is outside the contracted park pieces" % (tuple(round(c, 1) for c in p[:2]),))
                    break
    areas = [v for v in outs.get("ParkAreas", []) if isinstance(v, geo.Polygon)]
    if areas and sum(geo.area_m2(a) for a in areas) > geo.area_m2(park) + 1e-6:
        f.append("the vegetation areas exceed the park")
    return f


def check_record(rec, ops, official=None):
    import json
    import os
    from pypcg import stage_api
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
            continue
    params = {k: v for k, v in rec.get("params", {}).items() if k != stage_api.SEED}
    fails = check(inputs, params, outputs, ops, official)
    path = os.path.join(stage_api.RUNS_DIR, "s16_geometry.json")
    if os.path.exists(path):
        fails += ["geometry: " + x for x in check_geometry(json.load(open(path, encoding="utf-8")), ops)]
    return fails[:40]
