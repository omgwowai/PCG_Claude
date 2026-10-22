"""Stage 16 -- CentralParkVisuals (PCG_4_2_CentralPark_Visuals, 中央公园视觉): the GEOMETRY node.

Everything the official graph computes before its grammar, building, lake-mesh and terrain-writer nodes:
the park centre and the four transverse lines, the 1 cm road-centre outlines and the border-road segments,
the park pieces and their 8 m sidewalk ring, the walkpaths cut out of the drawn splines, the vegetation
areas, the two lakes (edge, water plane, -50 cm bed), the Met footprint and the exclusion polygons the
vegetation node needs. `docs/pypcg/stages/s16.md` section 2.1 names the official node behind every step;
the vegetation node is `s16_central_park_visuals`.

Inputs (kept scene reads): `Footprint` (`Get_Footprint_Actor`, role CentralParkFootprint), `DrawnSplines`
(`Get_Drawn_Splines`, tag USER_SPLINE), `Lake` (`Get_Lake`, tag LAKE), `ForestExclusion`
(`Get_Forest_Exclusion`, tag FOREST_EXCLUSION), `MeshTerrain` (`Subgraph_1`, Final: a surface).
"""
import math

from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import curves as C
from pypcg.geo import frames as F
from pypcg.geo import roads as R
from pypcg.geo import sections as SEC

STAGE = 16
RECORD = "s16_geometry"
DOC = """CentralParkVisuals (中央公园视觉), geometry: the park centre, four transverse lines and their 1 cm
outlines, the border-road segments, the park pieces and their 8 m sidewalk ring, the walkpaths cut from the
drawn splines, the vegetation areas, the two lakes (edge +20 cm, water plane at the lowest terrain height,
bed 50 cm below) and the Met footprint. Sizes in cm."""
RANDOM = False
EXACT_SPLINE_ROTATORS = True             # the Met footprint's rotations keep their doubles (convert._rotator_exact)
PARAMS = {}
INPUTS = {"Footprint": "spline", "DrawnSplines": "spline", "Lake": "spline", "ForestExclusion": "spline",
          "MeshTerrain": "surface"}
OUTPUTS = ("BorderSegments", "Corners", "SidewalkSegments", "Walkpaths", "LakeEdge", "Lake", "LakeBed",
           "MetFootprint", "ForestZone", "ParkAreas", "Exclusions")

# ---- the official settings (instance overrides) -----------------------------------------------------
LINE_LENGTH = 20500.0                    # Road_*_Line Length
LINES = (("65th", -38000.0, 87.0), ("79th", -10000.0, 94.0), ("86th", 4000.0, 88.0), ("97th", 26000.0, 93.0))
CENTRE_OUTLINE_CM = 1.0                  # Subgraph_8 Width
SIDEWALK_CONTRACT_CM = 800.0             # Subgraph_13 Contract
PATH_OUTLINE_CM = 800.0                  # Subgraph_17 Width
LAKE_EDGE_LIFT = (0.0, 0.0, 20.0)        # Offset_Lake_Z
LAKE_BED_DROP = (0.0, 0.0, -50.0)        # Subgraph_56
MET_POINT = (875.0, 1750.0, 50.0)        # Met_Point Location
MET_SHAPE_POSITION = (-5000.0, 5625.0, 50.0)   # Met_Footprint_Shape Position
MET_WIDTH, MET_LENGTH = 8000.0, 3750.0   # Met_Footprint_Shape Width (local X) / Length (local Y)
MET_EXPAND_CM = 1000.0                   # Expand_Met_Footprint Expand
RECT_ORDER = ((-1, 1), (1, 1), (1, -1), (-1, -1))   # Create_Spline_Shape Ngon 4 (stage 5's order)


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def _splines(inputs, pin, closed=None):
    out = []
    for v, _tags in inputs.get(pin, []):
        if isinstance(v, Spline) and len(v.points) >= 2 and (closed is None or bool(v.closed) == closed):
            out.append(v)
    return out


def _xy(points):
    return [(float(p[0]), float(p[1])) for p in points]


# ---- 1. the park centre -----------------------------------------------------------------------------
def rotator_quat(ops, pitch, yaw, roll):
    """`FRotator::Quaternion()`: the engine's own (`ops.rotator_quat`, SVML sincos) when the ops offer it, else
    `geo.assets.quat_of` (Python's sin / cos: the same rotation, possibly one ulp off)."""
    fn = getattr(ops, "rotator_quat", None)
    return tuple(fn(pitch, yaw, roll)) if fn is not None else AS.quat_of(pitch, yaw, roll)


EDGE_TIE_CM = 1e-6                       # edges this close in length are one length (see first_longest)


def first_longest(ring, tol=EDGE_TIE_CM):
    """`@Data.$LongestOuterSegmentIndex` where edges TIE: a rectangle's opposite edges are equal and the
    engine's strict `>` picks one by its own last bits; the first of the tied edges is the one it picked on
    the demo park (edge 0, yaw 34.2 -- the strict rule on Python's arithmetic picked edge 2, yaw -145.8, and
    turned every line and the Met by 180 degrees). Stage 15's `frame_edge` rule."""
    n = len(ring)
    lens = [math.dist(ring[k][:2], ring[(k + 1) % n][:2]) for k in range(n)]
    top = max(lens)
    return next(k for k, d in enumerate(lens) if d >= top - tol)


def centre(footprint, ops=None):
    """`Subgraph_0 Place_Point_AtCenter` (`Place_Point_AtCenter_CoreProcess_Loop`): the box centre of the
    footprint's control points at their z; its `$Rotation` is the ROTATOR of the polygon's point at the start
    of its first longest outer segment -- the CreatePolygon2D frame's quaternion times the segment's
    `MakeFromXZ` (`geo.frames.vertex_points`) -- with roll 0, turned back into a quaternion by
    `FRotator::Quaternion`. Returns `(loc, quat)`. Measured: (60 150, 57 100, 0); the rotator's yaw is
    34.22265945387145 (one ulp above `atan2` of the edge), and the engine's quaternion of it is the tapped one
    bit for bit (`pyg_probe_t22f_quat.py`); Python's sin / cos is one ulp off in z."""
    pts = [tuple(float(c) for c in p) for p in footprint.points]
    c = F.box_centre(pts)
    t, q = F.polygon_frame(pts)
    local = F.to_local(pts, t, q)
    _pos, rots = F.vertex_points(local, t, q)            # FSegment2d's unit direction, then MakeFromXZ
    pitch, yaw, _roll = F.rotator_of(rots[first_longest(local)])
    return (c[0], c[1], pts[0][2]), rotator_quat(ops, pitch, yaw, 0.0)


def compose(loc, quat, local):
    """`CopyPoints`' `FTransform` target x source with scale 1: rotate by the target's quaternion, then
    translate (`geo.place`'s order)."""
    d = geo.quat_rotate(quat, tuple(local))
    return (d[0] + loc[0], d[1] + loc[1], d[2] + loc[2])


# ---- 2. the transverse lines ------------------------------------------------------------------------
def lines(loc, quat, ops=None):
    """`Road_*_Line` (`Create_Spline_line`, `AtWorldOrigin` false): the points (-L/2, 0, 0) and (+L/2, 0, 0),
    turned by the node's yaw and moved by its `Position` (`CopyPoints_1`), then composed with the centre
    point (`CopyPoints_2`): one linear open 2-point line each, in the official order 65th, 79th, 86th, 97th."""
    out = []
    for _name, x, yaw in LINES:
        q = rotator_quat(ops, 0.0, yaw, 0.0)          # MakeTransformAttribute_1: FQuat(FRotator)
        ends = []
        for s in (-0.5, 0.5):
            p = geo.quat_rotate(q, (s * LINE_LENGTH, 0.0, 0.0))
            p = (p[0] + x, p[1], p[2])
            ends.append(compose(loc, quat, p))
        out.append(ends)
    return out


# ---- 3-4. the road-centre outlines and the border-road segments --------------------------------------
def centre_outlines(line_paths, footprint_ring, ops):
    """`Subgraph_8 Transform_Outline` (Width 1): each open line's band (`ForceOpen`, the FULL width), then the
    closed footprint's annulus (`ForceClosed`: grown less shrunk by half the width). Five polygons."""
    out = []
    for path in line_paths:
        out += R.outline(_xy(path), CENTRE_OUTLINE_CM, ops)
    out += R.outline_ring(_xy(footprint_ring), CENTRE_OUTLINE_CM, ops)
    return out


def edge_segments(polys, z=0.0):
    """`Extract_Segments` with `CutAngleThreshold` 0 (the primitive's default): every control point cuts, so a
    polygon gives one two-point segment per edge of its control points as `GetSplineControlPoints` lists them --
    the outer ring then each hole as ONE cyclic sequence (the annulus' two jumps between outer and hole are
    segments too). Degenerate edges are kept. Measured: the 28 border segments (t07) in this order."""
    out = []
    for p in polys:
        verts = [tuple(q[:2]) for q in p.outer]
        for h in p.holes:
            verts += [tuple(q[:2]) for q in h]
        n = len(verts)
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            out.append([(a[0], a[1], z), (b[0], b[1], z)])
    return out


# ---- 5-6. the pieces and the sidewalk ring ------------------------------------------------------------
def pieces(footprint_ring, outlines, ops):
    """`Subgraph_3 Compose_Areas_Exclusion`: the footprint less the five outlines."""
    park = Polygon(_xy(footprint_ring), [], 0.0)
    return [Polygon(p.outer, p.holes, 0.0) for p in A.exclusion([park], outlines, ops)]


def sidewalk_ring(parts, ops):
    """`Subgraph_13 Transform_Areas_Contract` (800; `UnionBeforeOutputting` false, the primitive's default),
    each piece in its own CreatePolygon2D frame (trap 64)."""
    out = []
    for p in parts:
        out += A.in_frame(p, lambda q: A.contract([q], SIDEWALK_CONTRACT_CM, ops, union=False))
    return [Polygon(p.outer, p.holes, 0.0) for p in out]


# ---- 7-8. the walkpaths and the vegetation areas -------------------------------------------------------
def flattened(spline):
    """`AttributeMathsOp_0/1/2` (Set `$Position.Z`, the second operand unwired: 0): the control points at
    z 0, the tangents and the polyline's XY kept."""
    pts = [(float(p[0]), float(p[1]), 0.0) for p in spline.points]
    poly = [(float(p[0]), float(p[1]), 0.0) for p in (spline.polyline or spline.points)]
    tans = [(tuple(a), tuple(b)) for a, b in spline.tangents] if spline.tangents else None
    return Spline(pts, closed=spline.closed, linear=spline.linear, tangents=tans, polyline=poly)


def walkpaths(drawn, rings, ops):
    """`Subgraph_20 Compose_Spline_Cut` (Intersection) of each flattened drawn spline with the contracted
    pieces: its polyline clipped (`geo.sections.cut_paths`), and each kept run `SplitSpline` of the curved
    spline between the keys nearest the run's ends (`geo.curves.split`). Each spline's pieces LAST FIRST, as
    `ClipPaths` hands them back (t12)."""
    out = []
    for s in drawn:
        if s.linear or not s.tangents or len(s.points) < 2:
            continue
        path = [(p[0], p[1], 0.0) for p in (s.polyline or s.points)]
        runs = SEC.cut_paths([path], [r.outer for r in rings], ops, inside=True)
        mine = []
        for run in runs:
            a = (run[0][0], run[0][1], 0.0)
            b = (run[-1][0], run[-1][1], 0.0)
            k0 = C.nearest_key(s.points, s.tangents, False, a)
            k1 = C.nearest_key(s.points, s.tangents, False, b)
            if k1 < k0:
                k0, k1 = k1, k0
            pts, tans = C.split(s.points, s.tangents, k0, k1)
            if len(pts) >= 2:
                mine.append((k0, Spline(pts, closed=False, linear=False, tangents=tans)))
        mine.sort(key=lambda t: -t[0])
        out += [sp for _k, sp in mine]
    return out


def vegetation_areas(parts, drawn, ops):
    """`Subgraph_17 Transform_Outline` (800) on each flattened drawn spline's polyline, then `Subgraph_18
    Compose_Areas_Exclusion`: the park pieces (NOT the contracted ones) less the bands."""
    bands = []
    for s in drawn:
        bands += R.outline(_xy(s.polyline or s.points), PATH_OUTLINE_CM, ops)
    areas = A.exclusion(parts, bands, ops)
    return [Polygon(p.outer, p.holes, 0.0) for p in areas], bands


# ---- 9. the lakes ----------------------------------------------------------------------------------------
def _tangents(s):
    return [(tuple(a), tuple(b)) for a, b in s.tangents] if s.tangents else \
        [(t, t) for t in C.auto_tangents(s.points, s.closed)]


def lake_edge(lake):
    """`Offset_Lake_Z` (+20, per point) then `Subgraph_16 Transform_Splines_Reverse`: a closed spline with
    explicit tangents -> `Subgraph_14` (SGD_Sidewalk_CITY_EDGE)."""
    flat = flattened(lake)
    pts, tans = C.offset_points(flat.points, _tangents(flat), True, LAKE_EDGE_LIFT)
    pts, tans = C.reverse(pts, tans)
    return Spline(pts, closed=True, linear=False, tangents=tans)


def lake_levels(lake, surface):
    """`Subgraph_44 Transform_Project` on `Offset_Lake_Z`'s +20 spline (each control point onto the terrain by
    a vertical ray; a miss keeps its z) -> `Subgraph_45 Transform_Level` (Min) -> `Subgraph_56 Transform_Offset` (-50). Returns `(water,
    bed)`: the water plane keeps the PROJECTED spline's auto tangents (Level moves positions only); the bed's
    tangents are auto again (`OffsetSpline` re-initialises a `CurveAuto` spline)."""
    flat = flattened(lake)
    lifted, _tans = C.offset_points(flat.points, _tangents(flat), True, LAKE_EDGE_LIFT)   # Subgraph_44 reads
    pts = []                                                                              # Offset_Lake_Z
    for p in lifted:
        h = surface.height(p[0], p[1]) if surface is not None else None
        pts.append((p[0], p[1], p[2] if h is None else h))
    tans = C.auto_tangents(pts, True)
    zmin = min(p[2] for p in pts)
    level = [(p[0], p[1], zmin) for p in pts]
    water = Spline(level, closed=True, linear=False, tangents=[(t, t) for t in tans])
    bed_pts, _ = C.offset_points(level, [(t, t) for t in tans], True, LAKE_BED_DROP)
    bed = Spline(bed_pts, closed=True, linear=False, tangents=None)     # CurveAuto: the engine recomputes them
    return water, bed


def area_polygon(spline):
    """A closed spline as `Compose_Shared_InputsProcessing` reads it: its polyline (1 cm error, the one
    `convert` reads) as a polygon, counter-clockwise."""
    ring = geo.drop_closing(_xy(spline.polyline or spline.points))
    return Polygon(geo.ccw(ring), [], 0.0)


# ---- 10. the Met -----------------------------------------------------------------------------------------
def met(loc, quat, surface, ops):
    """`Met_Point` (Create_Point onto the centre) -> `Met_Footprint_Shape` (the Ngon-4 rectangle on the point)
    -> `Subgraph_2` / `Subgraph_4` (project, level Min) -> `CreateSpline_0` (closed, linear): the building
    footprint; and `Expand_Met_Footprint` (+1000) on the UNPROJECTED rectangle: the exclusion polygon.
    Returns `(footprint_points, expanded_polygon, rectangle)`."""
    mp = compose(loc, quat, MET_POINT)
    rect = []
    for sx, sy in RECT_ORDER:
        local = (MET_SHAPE_POSITION[0] + sx * MET_WIDTH / 2.0, MET_SHAPE_POSITION[1] + sy * MET_LENGTH / 2.0,
                 MET_SHAPE_POSITION[2])
        rect.append(compose(mp, quat, local))
    zs = []
    for p in rect:
        h = surface.height(p[0], p[1]) if surface is not None else None
        zs.append(p[2] if h is None else h)
    zmin = min(zs)
    building = [(p[0], p[1], zmin) for p in rect]
    rotations = footprint_rotations([(p[0], p[1], z) for p, z in zip(rect, zs)])
    poly = Polygon(geo.ccw(_xy(rect)), [], rect[0][2])
    grown = A.in_frame(poly, lambda q: A.expand([q], MET_EXPAND_CM, ops))
    grown = [Polygon(p.outer, p.holes, rect[0][2]) for p in grown]
    return (building, rotations), grown, rect


def footprint_rotations(projected):
    """The control-point rotations `CreateSpline_0` carries into the building: `Transform_Project` hands the
    rectangle back as a CURVE spline (auto tangents of the projected corners), `Transform_Level` keeps those
    tangents, and `GetSplineControlPoints_0` writes each point's `MakeFromXZ(tangent, up)` -- pitch +-0.9 /
    +-1.4 deg on the demo (t28). `Assign_CitySampleBuildings` reads them (trap 63's kind): without them the
    footprint is bit for bit and the building's props still differ."""
    tans = C.auto_tangents(projected, True)
    return [F.rotator_of(F.make_from_xz(t, (0.0, 0.0, 1.0))) for t in tans]


# ---- the whole node ------------------------------------------------------------------------------------
def geometry(inputs, ops):
    """`({pin: [value]}, notes)`."""
    out = {pin: [] for pin in OUTPUTS}
    feet = _splines(inputs, "Footprint", closed=True)
    if not feet or ops is None:
        return out, ["no park footprint: nothing"]
    surface = _surface(inputs)
    fp = feet[0]
    ring = [tuple(float(c) for c in p) for p in fp.points]
    loc, quat = centre(fp, ops)
    line_paths = lines(loc, quat, ops)
    outl = centre_outlines(line_paths, ring, ops)
    out["BorderSegments"] = edge_segments(outl, 0.0)
    parts = pieces(ring, outl, ops)
    ring8 = sidewalk_ring(parts, ops)
    out["Corners"] = ring8
    out["SidewalkSegments"] = edge_segments(ring8, 0.0)
    drawn = [flattened(s) for s in _splines(inputs, "DrawnSplines")]
    out["Walkpaths"] = walkpaths(drawn, ring8, ops)
    areas, bands = vegetation_areas(parts, drawn, ops)
    out["ParkAreas"] = areas
    lakes = _splines(inputs, "Lake", closed=True)
    forest = _splines(inputs, "ForestExclusion", closed=True)
    excl = [area_polygon(s) for s in forest] + [area_polygon(s) for s in lakes]
    for lk in lakes:
        out["LakeEdge"].append(lake_edge(lk))
        water, bed = lake_levels(lk, surface)
        out["Lake"].append(water)
        out["LakeBed"].append(bed)
    out["ForestZone"] = [flattened(s) for s in forest]
    building, grown, _rect = met(loc, quat, surface, ops)
    out["MetFootprint"] = [building]
    out["Exclusions"] = excl + grown
    notes = ["centre (%.3f, %.3f) yaw %.6f; outlines %d, border segments %d; pieces %d, ring %d, sidewalk "
             "segments %d" % (loc[0], loc[1], math.degrees(2.0 * math.atan2(quat[2], quat[3])), len(outl),
                              len(out["BorderSegments"]), len(parts), len(ring8), len(out["SidewalkSegments"])),
             "drawn %d -> walkpaths %d, path bands %d, areas %d; lakes %d (water z %s); forest %d; Met z %.4f"
             % (len(drawn), len(out["Walkpaths"]), len(bands), len(areas), len(lakes),
                [round(w.points[0][2], 4) for w in out["Lake"]], len(forest), building[0][0][2])]
    return out, notes


def _spline_of(path, closed=False):
    return Spline([tuple(p) for p in path], closed=closed, linear=True)


def tagged(raw):
    out = {pin: [] for pin in OUTPUTS}
    out["BorderSegments"] = [(_spline_of(s), ["BorderSegments"]) for s in raw["BorderSegments"]]
    out["SidewalkSegments"] = [(_spline_of(s), ["SidewalkSegments"]) for s in raw["SidewalkSegments"]]
    out["Corners"] = [(p, ["Corners"]) for p in raw["Corners"]]
    out["MetFootprint"] = [(Spline([tuple(p) for p in b], closed=True, linear=True, rotations=list(r)), ["MetFootprint"])
                           for b, r in raw["MetFootprint"] if b]
    for pin in ("Walkpaths", "LakeEdge", "Lake", "LakeBed", "ForestZone", "ParkAreas", "Exclusions"):
        out[pin] = [(v, [pin]) for v in raw[pin]]
    return out


def run(inputs, params, ctx):
    raw, notes = geometry(inputs, ctx.ops)
    ctx.notes += notes
    return tagged(raw)
