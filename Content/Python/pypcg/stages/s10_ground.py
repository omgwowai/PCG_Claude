"""Stage 10 -- Ground (PCG_3_2_1_Ground, 地面与人行道).

The ground tiles under every buildable lot, and the shapes the three kept grammar nodes lay the
sidewalks, the sidewalk corners and the railings along. The official graph is 121 nodes (76 of them
computation); it publishes nothing -- its output node has no wired input -- so everything is
generated inside the graph, and so is the slim one: this module feeds the kept generation nodes only.
`docs/pypcg/stages/s10.md` names the official node behind every step.

The chain (official node names in brackets):

  TILES      Lots - (UndividableDistricts + LandmarkPark) [Subgraph_7] - reservedLots [Subgraph_22],
             each grown by 150 cm [Subgraph_10], filled with a 3 m grid in the frame of its longest
             edge [Subgraph_9 Fill_Areas_Uniformly], lifted 15 cm [Subgraph_33], fitted to the final
             mesh terrain [Subgraph_40 Custom_Projector_with_rotation_fix], split seven ways, one draw
             per lot piece [FC_RandomChoice_1..6], one plaza tile mesh per way, offset (-150, -150) so
             the mesh's corner pivot sits on the cell corner [AssignGroundTiles_A..G] -> `GroundTiles`
             -> the kept `Subgraph_32 Spawn ground tiles`
  SIDEWALKS  the City outline grown by half the artery width [AttributeMathsOp_1, Subgraph_23], as a
             closed linear spline [FilterDataByType_0, GetSplineControlPoints_0, CreateSpline_0],
             reversed [Subgraph_3], cut by the central park grown 19 m [Subgraph_52, Subgraph_49];
             with the Lots [Branch_1 Output A] cut at every corner over 20 degrees [Subgraph_8]; the
             landmark contracted 3 m [Subgraph_46] cut at every corner over 5 degrees [Subgraph_4]
             -> `SidewalkSegments` -> the kept `Subgraph_31 Assign Sidewalks`
  CORNERS    the boundary pieces, the Lots and the contracted landmark -> `CornerShapes` -> the kept
             `Subgraph_26 Assign Corners`
  RAILINGS   Lots x UndividableDistricts [Subgraph_14] - the landmark [Subgraph_29], lifted 21 cm
             [Subgraph_19] -> `RailingZones` -> the kept `Subgraph_20 Assign Railing And Fence Grammar`

The artery width arrives as a value: the official graph picks the Roads item whose tags contain
`Polygon` [FilterDataByTag_4] and reads its `@data.ArteryWidth` [ExtractAttribute_1]. A Python node
cannot read a data-domain attribute in this build, so those two nodes stay native and feed the
`ArteryWidth` pin; the halving is here.
"""
import math

from pypcg import geo
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G

STAGE = 10
DOC = """Ground (地面与人行道): the buildable lots (Lots less the undividable districts, the small landmark park and
the reserved lots) grown 1.5 m and tiled on a 3 m grid aligned with each piece's longest edge, fitted to
the final mesh terrain, split seven ways (one draw per piece) into the seven SM_Plaza_Square tiles; the
sidewalk lines (the City outline grown by half the artery width, cut by the central park, and every lot
edge and the landmark's contracted edge, cut at their corners); the corner shapes; and the railing zones
(lots inside undividable districts, less the landmark). The kept grammar and spawner nodes do the rest."""
RANDOM = True
PARAMS = {}
INPUTS = {"Lots": "area", "Districts": "area", "ArteryWidth": "param", "City": "spline",
          "MainTower": "polygon", "LandmarkPark": "polygon", "CentralParkFootprint": "polygon",
          "MeshTerrain": "surface"}
OUTPUTS = ("GroundTiles", "SidewalkSegments", "CornerShapes", "RailingZones")

# ---- the graph's fixed settings (instance overrides; anything not listed is the primitive default) ----
GROUND_EXPAND_CM = 150.0          # Subgraph_10 Expand ("slight expansion ... under the sidewalk")
TILE_EXTENT_CM = 150.0            # Subgraph_9 PointExtents: a 3 m cell
TILE_LIFT_CM = 15.0               # Subgraph_33 offset Z
RAILING_LIFT_CM = 21.0            # Subgraph_19 offset Z
PARK_BUFFER_CM = 1900.0           # Subgraph_52 Expand
LANDMARK_SETBACK_CM = 300.0       # Subgraph_46 Contract (UnionBeforeOutputting: primitive default, true)
LOT_CUT_DEG = 20.0                # Subgraph_8 CutAngleThreshold
LANDMARK_CUT_DEG = 5.0            # Subgraph_4 CutAngleThreshold
EXPAND_DEFAULT_CM = 100.0         # Transform_Areas_Expand's own default, what Subgraph_23 uses unwired

# The seven-way split: FC_RandomChoice_1..6 (`Ratio`, RandomPerDataset = the primitive default true)
# each keep a share of what the previous one left; the last one's Unselected is the seventh way.
SPLIT_RATIOS = (0.14285714285714285, 0.16666666666666666, 0.2, 0.25, 0.3333333333333333, 0.5)
_MESH = "/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_%s.SM_Plaza_Square_%s"
# AssignGroundTiles_A..G, in the split's order (A takes FC_RandomChoice_1.Selected, ..., F the sixth
# Selected, G its Unselected). Each call assigns one static mesh with PositionOffset (-150, -150, 0).
TILE_CALLS = tuple((k, _MESH % (k, k)) for k in "ABCDEFG")
TILE_OFFSET = (-150.0, -150.0, 0.0)
GATHER_ORDER = "ABCDEGF"          # Gather_0's input order


# ---- inputs ----------------------------------------------------------------------------------------
def _first_number(items):
    """The first numeric value of the first param item (`ExtractAttribute_1`'s one-entry set)."""
    for v, _tags in items:
        values = getattr(v, "values", None) or {}
        for x in values.values():
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                return float(x)
    return None


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def read(inputs):
    """The stage's named inputs as areas (`Filter_Tags` = an exact tag match)."""
    lots_items = inputs.get("Lots", [])
    districts = inputs.get("Districts", [])
    return {"lots": A.areas_of(lots_items, "Lots"),                         # Subgraph_1
            "reserved": A.areas_of(lots_items, "reservedLots"),             # Subgraph_16
            "undividable": A.areas_of(districts, "UndividableDistricts"),   # Subgraph_5
            "city": A.areas_of(inputs.get("City", [])),
            "tower": A.areas_of(inputs.get("MainTower", [])),
            "small_park": A.areas_of(inputs.get("LandmarkPark", [])),
            "park": A.areas_of(inputs.get("CentralParkFootprint", [])),
            "artery": _first_number(inputs.get("ArteryWidth", []))}


# ---- tiles -----------------------------------------------------------------------------------------
def ground_areas(src, ops):
    """`Subgraph_7` (each lot less the undividable districts and the small landmark park, one clip
    union), `Subgraph_22` (less the reserved lots), `Subgraph_10` (each piece grown 150 cm, no union)."""
    pieces = A.exclusion(src["lots"], src["undividable"] + src["small_park"], ops)
    pieces = A.exclusion(pieces, src["reserved"], ops)
    return A.expand(pieces, GROUND_EXPAND_CM, ops)


def tile_points(area):
    """`Subgraph_9 Fill_Areas_Uniformly` then `Subgraph_33`'s +15 cm on one ground piece: a `Points`
    with the sampler's box (+-150 on every axis), steepness 1 and the frame's yaw."""
    locs, yaw = G.fill_uniform(area.outer, area.z, TILE_EXTENT_CM)
    pts = Points()
    e = TILE_EXTENT_CM
    for p in locs:
        pts.add((p[0], p[1], p[2] + TILE_LIFT_CM), rot=(0.0, yaw, 0.0), bounds_min=(-e, -e, -e),
                bounds_max=(e, e, e), steepness=1.0)
    return pts


def project(pts, surface):
    """`Subgraph_40 Custom_Projector_with_rotation_fix` on every point of a set (in place)."""
    if surface is None:
        return pts
    for i in range(len(pts)):
        res = G.project_tile(pts.loc[i], pts.rot[i], pts.bounds_min[i], pts.bounds_max[i], surface)
        if res is not None:
            pts.loc[i], pts.rot[i] = res
    return pts


def split_seven(n, rng):
    """`FC_RandomChoice_1..6` (RandomPerDataset): one draw per remaining piece at each step. Returns the
    way (0..6 = A..G) of each of the n pieces."""
    way = [6] * n
    left = list(range(n))
    for k, ratio in enumerate(SPLIT_RATIOS):
        keep = geo.keep_each(len(left), ratio, rng)
        way_k = [i for i, f in zip(left, keep) if f]
        for i in way_k:
            way[i] = k
        left = [i for i, f in zip(left, keep) if not f]
    return way


def assign_tiles(sets, way, table):
    """`AssignGroundTiles_A..G`: each call merges its pieces' points (`$Seed += dataIndex`, the piece's
    index in that call's input) and assigns its one static mesh -- the primitive's output is then the
    moved targets alone, with the mesh's box. Returns `{letter: Points}` for the calls that got points."""
    out = {}
    for k, (letter, path) in enumerate(TILE_CALLS):
        mine = [sets[i] for i in range(len(sets)) if way[i] == k]
        targets = Points()
        for idx, s in enumerate(mine):
            for j in range(len(s)):
                targets.add(s.loc[j], rot=s.rot[j], scale=s.scale[j], density=s.density[j],
                            bounds_min=s.bounds_min[j], bounds_max=s.bounds_max[j], color=s.color[j],
                            steepness=s.steepness[j], seed=AS._i32(int(s.seed[j]) + idx))
        if not len(targets):
            continue
        items = AS.expand_items(targets, [table[k]], [0] * len(targets), {"position_offset": TILE_OFFSET})
        if items:
            out[letter] = items[-1]
    return out


def tiles(src, surface, ops, rng, loader):
    """The whole tile chain; returns `([(letter, Points)] in Gather_0's order, pieces, tile sets, ways)`."""
    pieces = ground_areas(src, ops)
    sets = [project(tile_points(p), surface) for p in pieces]
    way = split_seven(len(sets), rng)
    if loader is None or not any(len(s) for s in sets):
        return [], pieces, sets, way
    table = loader([path for _k, path in TILE_CALLS])
    by = assign_tiles(sets, way, table)
    return [(k, by[k]) for k in GATHER_ORDER if k in by], pieces, sets, way


# ---- sidewalks, corners, railings ------------------------------------------------------------------
def _spline(path, z, closed=False):
    return Spline([(float(p[0]), float(p[1]), float(z)) for p in path], closed=closed, linear=True)


def _yaw(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def boundary(src, ops):
    """`AttributeMathsOp_1` + `Subgraph_23`: the City grown by half the artery width; then its outer
    vertices as a closed linear spline, reversed [`GetSplineControlPoints_0`, `CreateSpline_0`,
    `Subgraph_3`], and cut by the central park grown 19 m [`Subgraph_52`, `Subgraph_49 Compose_Spline_Cut`,
    ClipPaths(Difference)]. Returns `[(path, closed, z, yaws)]`.

    `yaws` are the control points' own rotations, which the corner grammar reads (s10.md 2.3): each
    vertex keeps the yaw `GetSplineControlPoints_0` gave it -- the direction of its OUTGOING edge on
    the counter-clockwise grown ring -- through `CreateSpline_0` and `Subgraph_3`'s reverse (which
    keeps every point's rotation); a point `ClipPaths` makes on an edge takes `SplitSpline`'s
    `GetQuaternionAtSplineInputKey` there, the reversed spline's direction of travel."""
    half = src["artery"] / 2.0 if src["artery"] is not None else EXPAND_DEFAULT_CM
    grown = []
    for c in src["city"]:
        grown += A.in_frame(c, lambda p: A.expand([p], half, ops))
    park = A.expand(src["park"], PARK_BUFFER_CM, ops)
    out = []
    for g in grown:
        ccw = [tuple(p[:2]) for p in g.outer]
        n = len(ccw)
        if n < 2:
            continue
        own = {ccw[i]: _yaw(ccw[i], ccw[(i + 1) % n]) for i in range(n)}
        ring = list(reversed(ccw))
        cut_rings = [p.outer for p in park]
        hit = any(_crosses(ring, r) for r in cut_rings)
        if not hit:
            out.append((ring, True, g.z, [own[q] for q in ring]))
            continue
        pieces = [ring + [ring[0]]]
        for r in cut_rings:
            nxt = []
            for path in pieces:
                nxt += geo.clip_path(path, r, keep_inside=False)
            pieces = nxt
        # ClipPaths hands the pieces back last first (measured on the demo level's two pieces: the one
        # that ends on the path's end comes before the one that starts on its start).
        for piece in reversed(pieces):
            if len(piece) < 2:
                continue
            piece = [tuple(q[:2]) for q in piece]
            yaws = []
            for k, q in enumerate(piece):
                if q in own:
                    yaws.append(own[q])
                elif k == 0:
                    yaws.append(_yaw(q, piece[1]))
                else:
                    yaws.append(_yaw(piece[k - 1], q))
            out.append((piece, False, g.z, yaws))
    return out


def _crosses(ring, clip):
    """True when the closed ring and the clip ring cross or one holds the other's first vertex."""
    pieces = geo.clip_path(list(ring) + [ring[0]], clip, keep_inside=True)
    return bool(pieces)


def segments_of(path, closed, angle):
    """`Extract_Segments`: the straight runs between the control points that turn by more than `angle`;
    a closed shape wraps (`geo.extract_segments`), an open one keeps its two ends as cuts."""
    if closed:
        return geo.extract_segments(list(path), angle)
    return G.extract_open_segments(list(path), angle)


def sidewalks(src, ops, bound):
    """`SidewalkSegments` and `CornerShapes` values, in the official input order."""
    landmark = []
    for t in src["tower"]:                       # in the polygon's own frame: the ring's start vertex
        landmark += A.in_frame(t, lambda p: A.contract([p], LANDMARK_SETBACK_CM, ops))
    segs, corners = [], []
    for path, closed, z, yaws in bound:                                     # Branch_1 Output A, first part
        segs += [_spline(s, z) for s in segments_of(path, closed, LOT_CUT_DEG)]
        piece = _spline(path, z, closed=closed)
        piece.rotations = [(0.0, y, 0.0) for y in yaws]
        corners.append(piece)
    for lot in src["lots"]:                                                 # Branch_1 Output A, the Lots
        segs += [_spline(s, lot.z) for s in segments_of(lot.outer, True, LOT_CUT_DEG)]
        corners.append(lot)
    for lm in landmark:                                                     # Subgraph_4 / Subgraph_46
        segs += [_spline(s, lm.z) for s in segments_of(lm.outer, True, LANDMARK_CUT_DEG)]
        corners.append(lm)
    return segs, corners


def railings(src, ops):
    """`Subgraph_14` (each lot x the undividable districts), `Subgraph_29` (less the landmark),
    `Subgraph_19` (+21 cm: `Transform_Offset` moves a polygon's control points)."""
    zone = A.intersection(src["lots"], src["undividable"], ops) if src["undividable"] else []
    zone = A.exclusion(zone, src["tower"], ops)
    return [Polygon(list(p.outer), [list(h) for h in p.holes], p.z + RAILING_LIFT_CM) for p in zone]


def run(inputs, params, ctx):
    out = {pin: [] for pin in OUTPUTS}
    src = read(inputs)
    loader = getattr(ctx.ops, "assets", None)
    placed, pieces, sets, way = tiles(src, _surface(inputs), ctx.ops, ctx.rng, loader)
    for letter, pts in placed:
        out["GroundTiles"].append((pts, ["GroundTiles", "SM_Plaza_Square_" + letter]))
    ctx.notes.append("ground: %d pieces, %d tiles, ways %s" % (
        len(pieces), sum(len(s) for s in sets),
        "/".join(str(sum(len(s) for s, w in zip(sets, way) if w == k)) for k in range(7))))
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): no tiles assigned")
    bound = boundary(src, ctx.ops) if src["city"] else []
    segs, corners = sidewalks(src, ctx.ops, bound)
    out["SidewalkSegments"] = [(s, ["SidewalkSegments"]) for s in segs]
    out["CornerShapes"] = [(c, ["CornerShapes"]) for c in corners]
    out["RailingZones"] = [(p, ["RailingZones"]) for p in railings(src, ctx.ops)]
    ctx.notes.append("sidewalks: %d boundary pieces, %d segments, %d corner shapes, %d railing zones"
                     % (len(bound), len(segs), len(corners), len(out["RailingZones"])))
    return out
