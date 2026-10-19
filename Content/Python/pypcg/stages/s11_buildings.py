"""Stage 11 -- Buildings (PCG_3_3_1_Buildings, 建筑): the footprints' heights, terrain fit and shape split.

The official graph is 176 nodes (97 of them computation); `docs/pypcg/stages/s11.md` names the official node
behind every step. This is the stage's MAIN Python node; `s11_buildings_lots` runs before the native texture
writes and `s11_buildings_rooftops` after the native building nodes.

The chain, per class (official node names in brackets; Small / Medium / Large):

  READ      the class footprints after the NATIVE texture write [Subgraph_2_*District], and their
            `@data.MaxHeight` through a native ExtractAttribute adapter (a Python node cannot read a
            data-domain attribute)
  HIGHRISE  each footprint fully inside the HighRise zones [Subgraph_6 / 42 / 44 Filter_Areas_within_Areas]
            gets the mean, over its vertices, of the 3D distance to the zones' outline sampled every
            100 cm, remapped from the class's own min..max to 1..5 [Subgraph_7 / 43 / 45 Write_DistanceFrom,
            AttributeReduce_0 / 1 / 2 (Average)], times its height [AttributeMathsOp_0 / 7 / 8]; the
            selected first, then the rest [Gather_0 / 1 / 2]
  FIT       every vertex dropped onto the final mesh terrain [Subgraph_12_* Transform_Project], then all
            set to the lowest [Subgraph_13_* Transform_Level (Min)]: a closed linear spline per footprint
  SHAPES    (Medium / Large, ComplexBuildingShapes) the footprint as CreatePolygon2D makes it, larger than
            800 / 500 m2 [Subgraph_37 / 34 Filter_Areas_BySize], cleaned and square (4 corners of 90
            degrees, sides within 1:2) [Subgraph_35 / 32 FilterSquareShapes], taller than 2500 / 3500
            [FilterDataByAttribute_0 / 1]: medium ones a new height 2500..7000 [Subgraph_38 Write_Noise]
            x 2 [AttributeMathsOp_2], large ones x 1.3 [AttributeMathsOp_1] -> the complex-shape nodes
  OUT       the rest -> the kept Assign_CitySampleBuildings [Subgraph_3 / 40 / 41], each footprint's
            height written back to `@data.MaxHeight` by a native CopyAttributes adapter
  COLLISION the kept collision loops [Loop_5 / 4 / 3] get NOTHING: officially they run only on Branch_9/10/11's
            Output B (Partitioned true) and then CollisionGeometry; the slim graph drops Partitioned as false,
            so the collision streams stay empty whatever CollisionGeometry says (ruling T20a: the loops write
            actors and assets under /CitySamplePCG/Levels/Collision, which the official graph does not here)
"""
import json
import math
import os

from pypcg import geo
from pypcg.geo import ParamSet, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import frames as F
from pypcg.stage_api import Param

STAGE = 11
DOC = """Buildings (建筑): each district class's building footprints get a height from a noise texture,
raised by up to five times inside the HighRise zones (more the farther from the zone's edge), are fitted
to the final mesh terrain at their lowest point, and become City Sample buildings; with ComplexBuildingShapes
the large, square, tall medium and large footprints get complex building shapes instead. Each building's
rooftop outline is published by class (SmallRooftops / MediumRooftops / LargeRooftops) for the rooftop stage."""
RANDOM = True
PARAMS = {
    "MinHeightSmallDistrict": Param(2000.0, "Minimum building height for small districts", type="Double"),
    "MaxHeightSmallDistrict": Param(3000.0, "Maximum building height for small districts", type="Double"),
    "MinHeightMediumDistrict": Param(2500.0, "Minimum building height for medium districts", type="Double"),
    "MaxHeightMediumDistrict": Param(6000.0, "Maximum building height for medium districts", type="Double"),
    "MinHeightLargeDistrict": Param(5000.0, "Minimum building height for large districts", type="Double"),
    "MaxHeightLargeDistrict": Param(15000.0, "Maximum building height for large districts", type="Double"),
    "ComplexBuildingShapes": Param(False, "", type="Bool"),
    "CollisionGeometry": Param(False, "", type="Bool"),
}
CLASSES = ("Small", "Medium", "Large")
INPUTS = {"SmallLots": "area", "MediumLots": "area", "LargeLots": "area",
          "SmallHeights": "param", "MediumHeights": "param", "LargeHeights": "param",
          "HighRise": "spline", "MeshTerrain": "surface"}
STREAMS = ("SmallFootprints", "MediumFootprints", "LargeFootprints", "MediumComplex", "LargeComplex",
           "SmallCollision", "MediumCollision", "LargeCollision")
OUTPUTS = tuple(x for s in STREAMS for x in (s, s + "Heights")) + ("SpawnMeshes",)
HEIGHT = "MaxHeight"

# ---- the graph's fixed settings ------------------------------------------------------------------
MAX_DISTANCE_CM = 100000.0         # Subgraph_7 / 43 / 45 MaximumDistance
REMAP = (1.0, 5.0)                 # RemapOutputMin / RemapOutputMax (UseRemap)
SAMPLE_MAX_CM = 100.0              # Write_DistanceFrom_SplineLoop: increment = clamp(length / 100, 1, 100)
SIZE_M2 = {"Medium": 800.0, "Large": 500.0}             # Subgraph_37 / 34 (Operator Greater)
SQUARE_RATIO = 2.0                 # Subgraph_35 / 32 ratioLimit (Lesser)
TALL = {"Medium": 2500.0, "Large": 3500.0}               # FilterDataByAttribute_0 / 1 (Greater)
NOISE = (2500.0, 7000.0)           # Subgraph_38 Write_Noise (Set) NoiseMin / NoiseMax
SCALE = {"Medium": 2.0, "Large": 1.3}                    # AttributeMathsOp_2 / AttributeMathsOp_1
CLEAN_FUSE_CM = 1.0e-4             # CleanSpline ColocationDistanceThreshold (UE_KINDA_SMALL_NUMBER)
CLEAN_ANGLE_DEG = 5.0              # CleanSpline CollinearAngleThreshold
ANGLE_TOL = 1.0e-8                 # AttributeFilter Equal on doubles (UE_DOUBLE_SMALL_NUMBER)


# The oracle (V1, s11.md 6): a JSON file {"noise": [official Write_Noise values]} named by this variable makes
# the node use the official draws instead of its own, so the native building nodes can be compared with the
# official ones instance for instance. Unset on every shipped run.
ORACLE_ENV = "PYPCG_S11_ORACLE"


class Draws:
    """Every random choice of this node, in one place (stage 9's design), so a check can substitute the
    official outcome: `noise(n)` is `Subgraph_38 Write_Noise` (one value per medium complex footprint)."""

    def __init__(self, rng, noise_values=None):
        self.rng = rng
        self.noise_values = noise_values

    def noise(self, n):
        if self.noise_values is not None:
            if len(self.noise_values) != n:
                raise ValueError("oracle noise has %d values for %d footprints" % (len(self.noise_values), n))
            return list(self.noise_values)
        lo, hi = NOISE
        return [self.rng.uniform(lo, hi) for _ in range(n)]


def draws_for(rng):
    """`Draws`, with the official noise when the oracle variable names a file."""
    path = os.environ.get(ORACLE_ENV)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return Draws(rng, json.load(fh).get("noise")), "oracle draws from %s" % path
    return Draws(rng), None


class Footprint:
    """One footprint between the nodes: its control points (x, y, z), the vertices' engine quaternions, its
    height and the tags it was read with."""

    def __init__(self, points, quats, height, tags, index=None, base=None, selected=False):
        self.points = list(points)
        self.quats = list(quats)
        self.height = float(height)
        self.tags = list(tags)
        self.index = index              # the footprint's place in its class's input (the texture write's order)
        self.base = base                # its texture height
        self.selected = selected        # inside the HighRise zones

    def spline(self):
        return Spline([tuple(p) for p in self.points], closed=True, linear=True,
                      rotations=[F.rotator_of(q) for q in self.quats])


# ---- reads ---------------------------------------------------------------------------------------
def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def heights(items):
    """The `@data.MaxHeight` of each footprint, from the ExtractAttribute adapter's param data (one per
    footprint, the footprints' order)."""
    out = []
    for v, _tags in items:
        if isinstance(v, ParamSet):
            out.append(float(v.values.get(HEIGHT, next(iter(v.values.values()), 0.0))))
    return out


def ring_points(poly):
    """The 3D vertices the engine's ToPoint reads off a polygon (`Polygon.vertices`, else outer at z).
    `vertices` describes the polygon as the engine handed it over; it is only valid while `outer` is the one
    read with it (the stage never edits its input footprints)."""
    if poly.vertices:
        return [tuple(p) for p in poly.vertices]
    return [(p[0], p[1], poly.z) for p in poly.outer]


def ring_quats(poly, points):
    """The vertices' rotations: each outgoing segment's `MakeFromXZ(direction, up)` composed with the frame
    (`GetTransformAtDistance`); offline (no frame) the world directions."""
    if poly.frame:
        t, q = poly.frame[0], poly.frame[1]
        local = F.to_local(points, t, q)
        return F.vertex_points(local, t, q)[1]
    n = len(points)
    out = []
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        out.append(F.make_from_xz((b[0] - a[0], b[1] - a[1], 0.0), F.UP))
    return out


# ---- HighRise --------------------------------------------------------------------------------------
def zone_areas(items):
    """`Filter_Areas_within_Areas`' clip polygons: each closed HighRise spline as CreatePolygon2D makes it
    (its 1 cm polyline; `geo.areas.area_of`)."""
    return A.areas_of(items)


def zone_samples(items):
    """`Write_DistanceFrom_SplineLoop` on each HighRise spline: `SplineSampler` (Distance, bFitToCurve) at
    min(100, max(1, length / 100)) cm, every sample's world position."""
    out = []
    for v, _tags in items:
        if not isinstance(v, Spline) or len(v.points) < 2:
            continue
        curve = F.SplineCurve.of(v)
        step = min(SAMPLE_MAX_CM, max(1.0, curve.length() / 100.0))
        out += curve.sample_distance(step)
    return out


def within(polys, zones, ops):
    """`Filter_Areas_Within_Areas_CoreProcess_innerLoop` (IncludePartiallyContainedAreas false): a footprint
    is selected when its intersection with the zones' union is not empty and the first piece's floored area
    equals the footprint's own floored area."""
    flags = []
    cut = A.rings(zones)
    for p in polys:
        if not cut:
            flags.append(False)
            continue
        pieces = ops.intersection([p.outer] + list(p.holes), cut)
        flags.append(bool(pieces) and math.floor(A.area_cm2(pieces[0])) == math.floor(A.area_cm2(p)))
    return flags


def _nearest(v, samples):
    best = MAX_DISTANCE_CM * MAX_DISTANCE_CM
    for s in samples:
        dx, dy, dz = s[0] - v[0], s[1] - v[1], s[2] - v[2]
        d = dx * dx + dy * dy + dz * dz
        if d < best:
            best = d
    return math.sqrt(best)


def distance_factors(rings, samples):
    """`Write_DistanceFrom` (UseRemap, 1..5) then `AttributeReduce` (Average) per footprint: each vertex's
    3D distance to the nearest zone sample (`PCGDistance`, Center/Center, capped at MaximumDistance),
    remapped from the min..max over every vertex of the class to 1..5 (`AttributeRemap`: slope x (v - min) +
    1), averaged as `sum x float(1 / n)` over the vertices in the rebuilt polygon's attribute order (the
    distance polygon is rebuilt from its points sorted by descending index)."""
    dists = [[_nearest(v, samples) for v in ring] for ring in rings]
    flat = [d for ds in dists for d in ds]
    if not flat:
        return []
    lo, hi = min(flat), max(flat)
    out_lo, out_hi = REMAP
    if hi - lo == 0:
        slope, icpt = 0.0, (out_lo + out_hi) / 2.0
    else:
        slope, icpt = (out_hi - out_lo) / (hi - lo), out_lo
    out = []
    for ds in dists:
        vals = [slope * (d - lo) + icpt for d in reversed(ds)]
        s = 0.0
        for x in vals:
            s += x
        out.append(s * F.f32(1.0 / len(vals)))
    return out


# ---- terrain fit -----------------------------------------------------------------------------------
def fit(points, surface):
    """`Transform_Project` (positions) then `Transform_Level` (Min): each vertex's terrain height, then the
    lowest for all. A vertex the surface misses keeps its z."""
    zs = []
    for p in points:
        h = surface.height(p[0], p[1]) if surface is not None else None
        zs.append(p[2] if h is None else h)
    zmin = min(zs) if zs else 0.0
    return [(p[0], p[1], zmin) for p in points]


def footprints(polys, base, zone_items, ops, surface):
    """HIGHRISE and FIT for one class: [Footprint] in Gather order (selected first), and the selection."""
    zones = zone_areas(zone_items)
    flags = within(polys, zones, ops)
    sel = [i for i, f in enumerate(flags) if f]
    uns = [i for i, f in enumerate(flags) if not f]
    out = []
    if sel:
        samples = zone_samples(zone_items)
        rings = [ring_points(polys[i]) for i in sel]
        factors = distance_factors(rings, samples)
        for i, ring, k in zip(sel, rings, factors):
            pos, quats, _frame = F.rebuilt_vertices(ring[::-1])
            out.append(Footprint(fit(pos, surface), quats, base[i] * k, [], i, base[i], True))
    for i in uns:
        ring = ring_points(polys[i])
        out.append(Footprint(fit(ring, surface), ring_quats(polys[i], ring), base[i], [], i, base[i], False))
    return out, sel


# ---- the complex-shape split ----------------------------------------------------------------------
def as_polygon(fp):
    """The footprint as `CreatePolygon2D` reads its levelled spline (`frames.create_polygon_points`): the
    3D points, their stored frame and the polygon's vertices and rotations as ToPoint reads them."""
    n = len(fp.points)
    curve = F.SplineCurve(fp.points, [(0.0, 0.0, 0.0)] * n, [(0.0, 0.0, 0.0)] * n, [True] * n, True)
    pts = F.create_polygon_points(curve)
    pos, quats, (t, q) = F.rebuilt_vertices(pts)
    local = F.to_local(pts, t, q)
    return pts, pos, quats, abs(F.signed_area_2d(local))


def _collinear(a, b, thr):
    return abs(sum(x * y for x, y in zip(F.safe_normal(a), F.safe_normal(b)))) >= thr


def clean(points, quats):
    """`CleanSpline` (defaults) on a closed linear spline: fuse colocated points (KeepFirst), then remove a
    middle point whose four tangents lie within 5 degrees of the chord. Returns (points, quats)."""
    n = len(points)
    pts = [tuple(p) for p in points]
    rots = list(quats)
    arrive = [F._sub(pts[i], pts[i - 1]) for i in range(n)]
    leave = [F._sub(pts[(i + 1) % n], pts[i]) for i in range(n)]

    def prev(i, k):
        r = i - k
        while r < 0:
            r += len(pts)
        return r

    for i in range(len(pts) - 1, -1, -1):
        if i >= len(pts):
            continue
        p = prev(i, 1)
        d = F._sub(pts[p], pts[i])
        if d[0] * d[0] + d[1] * d[1] + d[2] * d[2] < CLEAN_FUSE_CM * CLEAN_FUSE_CM:
            leave[p] = leave[i]
            for col in (pts, rots, arrive, leave):
                del col[i]
    thr = max(abs(math.cos(math.radians(CLEAN_ANGLE_DEG))), 1.0e-8)
    i = len(pts) - 1
    while i >= 0:
        if len(pts) < 3:
            break
        if i >= len(pts):
            i -= 1
            continue
        a, b = prev(i, 2), prev(i, 1)
        chord = F._sub(pts[i], pts[a])
        if (_collinear(leave[a], chord, thr) and _collinear(arrive[b], chord, thr) and
                _collinear(leave[b], chord, thr) and _collinear(arrive[i], chord, thr)):
            leave[a] = F._sub(pts[i], pts[a])
            arrive[i] = leave[a]
            for col in (pts, rots, arrive, leave):
                del col[b]
        i -= 1
    return pts, rots


def square(points, quats):
    """`FilterSquareShapes`' three tests on a cleaned spline: 'count' (not 4 points), 'angle' (a turn that
    is not 90 degrees within 1e-8, measured from the control points' own yaws), 'ratio' (longest / shortest
    side not under 2), or None when it passes."""
    if len(points) != 4:
        return "count"
    yaws = [F.rotator_of(q)[1] for q in quats]
    for i in range(4):
        diff = yaws[i] - yaws[i - 1]
        nf = math.trunc(diff / 180.0)
        if abs((diff + nf * -360.0) - 90.0) > ANGLE_TOL:
            return "angle"
    sides = [math.dist(points[i], points[(i + 1) % 4]) for i in range(4)]
    if min(sides) <= 0 or not (max(sides) / min(sides) < SQUARE_RATIO):
        return "ratio"
    return None


def complex_split(cls, fps, draws):
    """SHAPES for Medium / Large: (to Assign_CitySampleBuildings, to AssignBuildingShape), each a list of
    (value, height) in the official order -- the small ones as polygons, then the squares' rejects
    (by count, angle, ratio), then the low squares, as cleaned splines."""
    small, by_reason, tall_out, tall_in = [], {"count": [], "angle": [], "ratio": []}, [], []
    for fp in fps:
        pts, pos, quats, area = as_polygon(fp)
        if not area > SIZE_M2[cls] * 1.0e4:
            small.append((Polygon([(p[0], p[1]) for p in pts], [], pts[0][2] if pts else 0.0), fp.height))
            continue
        cpts, cq = clean(pos, quats)
        spline = Spline(cpts, closed=True, linear=True, rotations=[F.rotator_of(q) for q in cq])
        why = square(cpts, cq)
        if why:
            by_reason[why].append((spline, fp.height))
        elif fp.height > TALL[cls]:
            tall_in.append((spline, fp.height))
        else:
            tall_out.append((spline, fp.height))
    if cls == "Medium":
        values = draws.noise(len(tall_in))
        tall_in = [(s, v * SCALE[cls]) for (s, _h), v in zip(tall_in, values)]
    else:
        tall_in = [(s, h * SCALE[cls]) for s, h in tall_in]
    to_assign = small + by_reason["count"] + by_reason["angle"] + by_reason["ratio"] + tall_out
    return to_assign, tall_in, {"small": len(small), "count": len(by_reason["count"]), "angle": len(by_reason["angle"]),
                                "ratio": len(by_reason["ratio"]), "low": len(tall_out), "complex": len(tall_in)}


# ---- the whole node ----------------------------------------------------------------------------------
def _height_set(h):
    return ParamSet({HEIGHT: float(h)}, {HEIGHT: "Double"})


def buildings(inputs, params, ops, draws):
    """{stream: [(value, height)]} and notes."""
    surface = _surface(inputs)
    zone_items = inputs.get("HighRise", [])
    streams = {s: [] for s in STREAMS}
    notes = []
    for cls in CLASSES:
        polys = [v for v, _t in inputs.get(cls + "Lots", []) if isinstance(v, Polygon)]
        base = heights(inputs.get(cls + "Heights", []))
        if len(base) != len(polys):
            notes.append("%s: %d footprints but %d heights; heights padded with 0" % (cls, len(polys), len(base)))
            base = (base + [0.0] * len(polys))[:len(polys)]
        fps, sel = footprints(polys, base, zone_items, ops, surface)
        notes.append("%s: %d footprints, %d in the HighRise zones" % (cls, len(fps), len(sel)))
        # The collision streams stay empty: Partitioned is dropped as false, and officially the collision loops
        # need it true before CollisionGeometry is even read (ruling T20a, s11.md 3.3).
        if cls != "Small" and params.get("ComplexBuildingShapes"):
            to_assign, to_shape, counts = complex_split(cls, fps, draws)
            streams[cls + "Footprints"] = to_assign
            streams[cls + "Complex"] = to_shape
            notes.append("%s shapes: %s" % (cls, ", ".join("%s %d" % kv for kv in counts.items())))
        else:
            streams[cls + "Footprints"] = [(fp.spline(), fp.height) for fp in fps]
    return streams, notes


def tagged(streams):
    out = {pin: [] for pin in OUTPUTS}
    for s, items in streams.items():
        out[s] = [(v, [s]) for v, _h in items]
        out[s + "Heights"] = [(_height_set(h), [s]) for _v, h in items]
    out["SpawnMeshes"] = [(ParamSet({"SpawnMeshes": True}, {"SpawnMeshes": "Bool"}), [])]
    return out


def run(inputs, params, ctx):
    draws, note = draws_for(ctx.rng)
    streams, notes = buildings(inputs, params, ctx.ops, draws)
    ctx.notes += ([note] if note else []) + notes
    return tagged(streams)
