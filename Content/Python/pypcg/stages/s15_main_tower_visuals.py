"""Stage 15 -- MainTowerVisuals (PCG_4_1_MainTower_Visuals, 主塔视觉).

The hero tower's dressing: two rings, three arms split off the outer one, the hexagons on the inner one,
a ring of trees, plaza tiles, and the footprints the kept building, mesh, grammar, fitting and spawn
nodes turn into the tower. The official graph is 120 nodes: 30 generation nodes (17
`Assign_CitySampleBuildings`, 3 `Create_Mesh_Planar`, 5 `Spawn_Assets`, 2 `Assign_ShapeGrammarDefinition`,
3 `Fill_Areas_WithFittingAssets_with_Corrective`) stay native, and the computation between them is Python.
It publishes nothing -- its output node is unwired -- so the slim graph has no `out()` call either.
`docs/pypcg/stages/s15.md` names the official node behind every step.

The computation interleaves with the native building nodes (a contract of one tower's rooftops is the next
tower's footprint), so it is split over six Python nodes. This one is everything upstream of the first
`Assign_CitySampleBuildings`; `s15_tower_level1` .. `3` are the contracts between the stacked towers (and
the courtyard), `s15_tower_top` the antenna, `s15_tower_sidewalk` the sidewalk projector.

The chain (official node names in brackets):

  SHAPE     the stage-4 footprint read back [Subgraph_35 Get_ActorDataByRef]: a closed 6-gon spline
  ALIGN     its box centre to the world origin, X Y AND Z [Subgraph_85, Justify_Z Center -> Same]
  OUTER     contracted 30 m [Subgraph_44] -> polygon [FilterDataByType_1, GetSplineControlPoints_1,
            CreatePolygon2D_1] -> "projected" [Subgraph_42: NO surface pin, a pass-through] -> levelled Min
            [Subgraph_43]: the ring at z ~ 0 the arms stand on
  ARMS      three bands [Subgraph_83, subdiv (1, 3)] -> the middle one [FilterDataByIndex_1 "1"] -> two
            halves [Subgraph_33, subdiv (2, 1)] -> BOTH turned -60 deg about the VOLUME's own location
            [Subgraph_34, Transform_Offset PerPoints false: the data frame is the component's transform]
            -> Reroute_2 -> +120 [Subgraph_37] and -120 [Subgraph_38]; each two-piece SET aligned to the
            input shape's box centre [Subgraph_89 / 88 / 86] -> its piece 0 [FilterDataByIndex_4 / 2 / 3]
  INNER     the aligned shape contracted 32.5 m [Subgraph_72] -> polygon -> projected onto the terrain
            [Subgraph_27] -> levelled Min [Subgraph_28] -> aligned to the input shape [Subgraph_87]: the
            CHC footprint (Reroute_0)
  HEXES     six 25 m hexagons [Subgraph_2 Create_Spline_Shape, Width = Length 2500 from CreateConstant_0],
            one per vertex of the INNER ring, each stage 4's 6-gon turned `yaw - 90` about that vertex,
            `yaw` the vertex's outgoing edge + 90 (`geo.frames.copy_shape`)
  TREES     the input shape contracted 500 cm [ContractTreeRing] -> a point every L / int(L / 1000)
            [PlaceTreesOnSpline, `geo.frames.sample_on_spline`] -> `Branch_0` on `UseMegaplantsTrees` ->
            `AssignTrees` (Megaplants) or `Subgraph_20` (field trees) [Assign_Assets] -> onto the terrain
            [Subgraph_30 Custom_Projector_with_rotation_fix] -> scale 1 for the tree bases
            [AttributeMathsOp_0]; roll and pitch 0 for the trees [AttributeMathsOp_2, _4]
  PLAZA     the input shape filled with 3 m cells [FillPlaza Fill_Areas_Uniformly, PointExtents 150] ->
            onto the terrain [Subgraph_29]
"""
import math

from pypcg import geo
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import frames as F
from pypcg.geo import ground as G
from pypcg.stage_api import Param

STAGE = 15
DOC = """MainTowerVisuals (主塔视觉): the hero tower's two rings (30 m and 32.5 m) and three arm sectors,
the six 25 m hexagons on the inner ring, the CHC 50 m footprint, a ring of trees every 10 m facing inward,
the plaza tiles filling the input shape, and the footprints the kept building, mesh, grammar, fitting and
spawn nodes turn into the tower's dressing. Publishes nothing."""
RANDOM = True
PARAMS = {
    "UseMegaplantsTrees": Param(False, "Use the Megaplants trees for the ring instead of the Black Alder "
                                       "field trees", type="Bool"),
}
# Volume: the stage-4 footprint (`Subgraph_35`); Self: this volume's own transform, the frame every
# `Transform_Offset` of the arm chain turns about; MeshTerrain: `Subgraph_26` (Final).
INPUTS = {"Volume": "spline", "Self": "points", "MeshTerrain": "surface"}
OUTPUTS = ("InnerRing", "Hexagons", "Sector90", "Sector80", "Sector70", "TreeBases", "Trees", "PlazaTiles")

# ---- the graph's fixed settings (instance overrides) ------------------------------------------------
OUTER_CONTRACT_CM = 3000.0         # Subgraph_44 Contract
INNER_CONTRACT_CM = 3250.0         # Subgraph_72 Contract
TREE_CONTRACT_CM = 500.0           # ContractTreeRing Contract
TREE_SPACING_CM = 1000.0           # PlaceTreesOnSpline Spacing
PLAZA_EXTENT_CM = 150.0            # FillPlaza PointExtents
HEX_SIDE_CM = 2500.0               # CreateConstant_0 FloatValue -> Subgraph_2 Width AND Length
SUBDIV_BANDS = (1, 3)              # Subgraph_83 SubdivWidth / SubdivLength
SUBDIV_HALVES = (2, 1)             # Subgraph_33 SubdivWidth / SubdivLength
BASE_TURN_DEG = -60.0              # Subgraph_34 rotationOffset Yaw
PLUS_TURN_DEG, MINUS_TURN_DEG = 120.0, -120.0   # Subgraph_37 / Subgraph_38
HEX_TURN_OFFSET_DEG = -90.0        # the copy's turn: the ring vertex's own yaw - 90 (36 tapped vertices, 0 cm)
PLAZA_MESH = "/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_A.SM_Plaza_Square_A"   # SpawnPlaza Assets

# The two Assign_Assets calls `Branch_0` chooses between (official overrides, keys as `geo.assets` reads them)
MEGA_TREES = tuple("/CitySamplePCG/Megaplants/Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_%s."
                   "SM_Black_Alder_01_%s" % (k, k) for k in "ABCD")                          # AssignTrees
MEGA_SETTINGS = {"scale_offset": {"X": 1.414055, "Y": 1, "Z": 1}, "random_scale_range": {"X": 0.33, "Y": 0, "Z": 0},
                 "uniform_scale": True, "use_mesh_bounds": True, "use_index_attribute": False,
                 "index_attribute": ""}
FIELD_TREES = tuple("/CitySamplePCG/BlackAlder/Geometry/PivotPainter/SM_BlackAlder_Field_%02d_PP."
                    "SM_BlackAlder_Field_%02d_PP" % (k, k) for k in (1, 2, 3, 4))           # Subgraph_20
FIELD_SETTINGS = {"extents_scale": {"X": 0.7, "Y": 1, "Z": 1}, "random_scale_range": {"X": 0.2, "Y": 0, "Z": 0}}


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def shape_of(inputs):
    """`Subgraph_35`: the stage-4 footprint, a closed spline -- its control points with their own z. A
    polygon (an offline fixture) is read as its outer ring. Empty pin -> []."""
    for v, _tags in inputs.get("Volume", []):
        if isinstance(v, Spline) and v.closed and len(v.points) >= 3:
            return [tuple(float(c) for c in p) for p in v.points]
        if isinstance(v, Polygon) and len(v.outer) >= 3:
            zs = v.zs if v.zs is not None else [v.z] * len(v.outer)
            return [(p[0], p[1], z) for p, z in zip(v.outer, zs)]
    return []


def pivot_of(inputs):
    """The data frame every spline of the arm chain carries: this volume's own location (`Self`, the
    `Get Actor Data GetSinglePoint` of the slim graph). Measured: the tapped frame translation
    (-613.8667, 142.0539, 2800) IS the stage-15 volume's location, and the -60 / +-120 turns are about it
    to 1e-12 cm (s15.md section 5). None when the pin is empty."""
    for v, _tags in inputs.get("Self", []):
        loc = getattr(v, "loc", None)
        if loc:
            return (float(loc[0][0]), float(loc[0][1]))
    return None


# ---- 1. align, 2. outer ring, 3. inner ring ---------------------------------------------------------
def aligned(points):
    """Subgraph_85 `Transform_Align`: the shape's box centre to the world origin (`Subgraph_84`), on X, Y
    AND Z (this one node has `Justify_Z_from` Center). The demo input already sits there: identity to
    4.9e-13 cm."""
    if not points:
        return []
    xy = F.align(points, (0.0, 0.0, 0.0))
    zc = F.box_centre(points)[2]
    return [(p[0], p[1], p[2] - zc) for p in xy]


def _contract_ring(points, distance, ops):
    """`Transform_Areas_Contract` on the ring, in its own frame (trap 64: the start vertex), as a ring of
    points at the ring's first z. A ring contracted to nothing gives []."""
    if len(points) < 3:
        return []
    poly = Polygon([(p[0], p[1]) for p in points], [], points[0][2])
    out = A.in_frame(poly, lambda q: A.contract([q], distance, ops))
    if not out:
        return []
    return [(q[0], q[1], poly.z) for q in out[0].outer]


def _polygon_ring(points):
    """FilterDataByType -> GetSplineControlPoints -> CreatePolygon2D -> Level Min: the polygon the ring
    becomes, read back as its vertices (`geo.frames.polygon_of`, the engine's own round trip), all at the
    lowest z."""
    if len(points) < 3:
        return []
    _poly, sp = F.polygon_of(points)
    verts = sp.vertices
    if not verts:
        return []
    zmin = min(v[2] for v in verts)
    return [(v[0], v[1], zmin) for v in verts]


def _project(points, surface):
    """Subgraph_27 (`Transform_Project`, terrain wired) then Subgraph_28 (`Transform_Level` Min)."""
    from pypcg.stages.s11_buildings import fit
    return fit(points, surface) if points else []


def outer_ring(base, ops):
    """Subgraph_44 -> polygon -> Subgraph_42 (NO surface: a pass-through; projecting would lift the
    ground layer 2535.83 cm) -> Subgraph_43 Min."""
    return _polygon_ring(_contract_ring(base, OUTER_CONTRACT_CM, ops))


def inner_ring(base, shape, ops, surface):
    """Subgraph_72 -> polygon -> Subgraph_27 / 28 -> Subgraph_87 (aligned to the input shape's box centre;
    despite its title it aligns the INNER ring). z 2041.2605 on the demo."""
    ring = _project(_polygon_ring(_contract_ring(base, INNER_CONTRACT_CM, ops)), surface)
    return F.align(ring, F.box_centre(shape)) if ring else []


# ---- 4. the arms -----------------------------------------------------------------------------------
EDGE_TIE_CM = 1e-6                 # edges this close are one length to the engine (see `frame_edge`)


def frame_edge(ring, tol=EDGE_TIE_CM):
    """The edge `Subdivide_Areas_withGrid` lays its grid from: the FIRST longest, edges within `tol` of the
    longest counted as equal. The engine's rule is a strict `>` over the edges; on a regular hexagon all six
    edges tie and the winner is a matter of last bits, which Python's arithmetic does not reproduce -- the
    fixture's outer ring has edge 2 longer than edge 0 by 3e-12 cm, yet the tapped bands are cut parallel to
    edge 0 (horizontal: t05's three bands at y -2619, 0, +2619). Equal-length edges first-wins does."""
    n = len(ring)
    lens = [math.dist(ring[i][:2], ring[(i + 1) % n][:2]) for i in range(n)]
    top = max(lens)
    return next(i for i, d in enumerate(lens) if d >= top - tol)


def _grid_pieces(ring, subdiv, ops):
    """`Subdivide_Areas_withGrid` in subdivision mode, then `CutWithPaths` by the whole grid lines (stage
    9's `grid`), in world coordinates: the pieces of ONE ring, each a ring of (x, y, z)."""
    if len(ring) < 3:
        return []
    z = ring[0][2]
    outer = [(p[0], p[1]) for p in ring]
    full = [seg for _a, seg in geo.grid_lines(outer, 0.0, 0.0, 100000.0, subdiv=subdiv, clipped=False,
                                              edge=frame_edge(outer))]
    pieces = ops.cut_with_paths(outer, full) if full else [outer]
    return [[(c[0], c[1], z) for c in r] for r in pieces]


def _centroid(ring):
    n = len(ring)
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)


def _band_order(pieces, axis, descending=False):
    """The piece ORDER the taps show (`Saved/t22/tap15_a.json`, re-read 2026-10-20): the 3-way split
    ascending along y (centroids -2619.03, 0, +2619.03: the centre band is index 1 for
    `FilterDataByIndex_1`); the 2-way split DESCENDING along x (+2419.04 then -2419.04)."""
    return sorted(pieces, key=lambda r: _centroid(r)[axis], reverse=descending)


def _align_set(pieces, target):
    """`Transform_Align` Center -> Center on a SET: every piece moved by the same shift, the set's box
    centre to `target`'s (measured on all three arms, 0 cm)."""
    allp = [p for pc in pieces for p in pc]
    if not allp:
        return [list(pc) for pc in pieces]
    c, t = F.box_centre(allp), F.box_centre(target) if target else (0.0, 0.0, 0.0)
    dx, dy = t[0] - c[0], t[1] - c[1]
    return [[(p[0] + dx, p[1] + dy, p[2]) for p in pc] for pc in pieces]


def arms(outer, shape, pivot, ops):
    """Subgraph_83 -> FilterDataByIndex_1 -> Subgraph_33 -> Subgraph_34 -> 37 / 38 -> 89 / 88 / 86 ->
    FilterDataByIndex_4 / 2 / 3. Returns {pin: ring}: the centre slice is the 90 m sector (Subgraph_40), the
    -120 arm the 80 m (Subgraph_38 -> 86 -> FilterDataByIndex_3 -> Subgraph_51), the +120 arm the 70 m
    (Subgraph_37 -> 88 -> FilterDataByIndex_2 -> Subgraph_58). Every tapped sector reproduced to 0 cm."""
    none = {"Sector90": [], "Sector80": [], "Sector70": []}
    if len(outer) < 3 or pivot is None:
        return none
    bands = _band_order(_grid_pieces(outer, SUBDIV_BANDS, ops), 1)
    if len(bands) < 2:
        return none
    halves = _band_order(_grid_pieces(bands[1], SUBDIV_HALVES, ops), 0, descending=True)
    if not halves:
        return none
    base = [F.rotate_in_frame(h, BASE_TURN_DEG, pivot) for h in halves]
    plus = [F.rotate_in_frame(h, PLUS_TURN_DEG, pivot) for h in base]
    minus = [F.rotate_in_frame(h, MINUS_TURN_DEG, pivot) for h in base]
    return {"Sector90": _align_set(base, shape)[0], "Sector80": _align_set(minus, shape)[0],
            "Sector70": _align_set(plus, shape)[0]}


# ---- 5. the hexagons -------------------------------------------------------------------------------
def hexagon_source(radius=HEX_SIDE_CM / 2.0):
    """Stage 4's own 6-gon, `ENGINE_DEG` order, at the 25 m hexagon's radius (Width / 2 = 1250)."""
    from pypcg.stages.s04_main_tower_footprint import ENGINE_DEG
    return [(-(radius * math.cos(math.radians(p))), -(radius * math.sin(math.radians(p)))) for p in ENGINE_DEG]


def ring_yaws(ring):
    """Each control point's yaw on a closed linear spline: the OUTGOING edge's direction + 90 degrees,
    normalised to (-180, 180]."""
    n = len(ring)
    out = []
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        y = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + 90.0
        out.append(y - 360.0 if y > 180.0 else y)
    return out


def hexagons(inner):
    """Subgraph_2 `Create_Spline_Shape` (6-gon, Width = Length 2500) copied onto the inner ring: one per
    ring vertex, turned `yaw - 90` about that vertex. Measured: all 36 tapped vertices to 0 cm (the
    `s15_fixture.json` `copy` block); a port that centres them on the CHC outline centres is 649.02 cm off."""
    if len(inner) < 3:
        return []
    src = hexagon_source()
    out = []
    for centre, yaw in zip(inner, ring_yaws(inner)):
        out.append([(p[0], p[1], centre[2]) for p in F.copy_shape(src, yaw + HEX_TURN_OFFSET_DEG, centre[:2])])
    return out


# ---- 6. the tree ring ------------------------------------------------------------------------------
def tree_samples(shape, ops):
    """ContractTreeRing (500, on the UNALIGNED input shape: NamedRerouteDeclaration_1) then
    `PlaceTreesOnSpline` (Spacing 1000, inward, FitToCurve): `[(x, y, yaw)]` and the ring's z."""
    ring = _contract_ring(shape, TREE_CONTRACT_CM, ops)
    if len(ring) < 3:
        return [], 0.0
    return F.sample_on_spline([(p[0], p[1]) for p in ring], TREE_SPACING_CM), ring[0][2]


def tree_points(samples, z):
    """The sampler's points: box +-1, scale 1, density 1, steepness 1, the seed `ComputeSeedFromPosition`
    gives (`PCGHelpers.cpp:50`)."""
    pts = Points()
    for x, y, yaw in samples:
        pts.add((x, y, z), rot=(0.0, yaw, 0.0), steepness=1.0, seed=AS.compute_seed(int(x), int(y), int(z)))
    return pts


def project(pts, surface):
    """`Custom_Projector_with_rotation_fix` on every point, in place; a point the surface misses keeps its
    place (the engine sets it density 0, which a covering terrain never does). No surface -> unchanged."""
    if surface is None:
        return pts
    q = pts.quat
    for i in range(len(pts)):
        res = G.project_tile(pts.loc[i], pts.rot[i], pts.bounds_min[i], pts.bounds_max[i], surface,
                             scale=pts.scale[i], quat=q[i] if q else None)
        if res is not None:
            pts.loc[i], pts.rot[i] = res
    pts.quat = None
    return pts


def _with(pts, fn):
    """A copy of `pts` with `fn(rot, scale) -> (rot, scale)` applied to every point."""
    out = Points()
    for name, tname in pts.types.items():
        out.declare(name, tname)
    for j in range(len(pts)):
        rot, scale = fn(pts.rot[j], pts.scale[j])
        kw = {name: col[j] for name, col in pts.attrs.items()}
        out.add(pts.loc[j], rot=rot, scale=scale, density=pts.density[j], bounds_min=pts.bounds_min[j],
                bounds_max=pts.bounds_max[j], color=pts.color[j], steepness=pts.steepness[j], seed=pts.seed[j], **kw)
    return out


def trees(samples, z, mega, surface, rng, loader):
    """`Branch_0` -> AssignTrees / Subgraph_20 -> Subgraph_30 -> (AttributeMathsOp_0: the tree bases,
    `$Scale` 1) and (AttributeMathsOp_2 / 4: the trees, roll and pitch 0). Returns (bases, trees), each a
    list of point sets in the assign call's item order."""
    if not samples or loader is None:
        return [], []
    paths, settings = (MEGA_TREES, MEGA_SETTINGS) if mega else (FIELD_TREES, FIELD_SETTINGS)
    items = AS.expand_items(tree_points(samples, z), loader(list(paths)), None, dict(settings, rng=rng))
    projected = [project(p, surface) for p in items if len(p)]
    bases = [_with(p, lambda r, s: (r, (1.0, 1.0, 1.0))) for p in projected]
    upright = [_with(p, lambda r, s: ((0.0, r[1], 0.0), s)) for p in projected]
    return bases, upright


# ---- 7. the plaza ----------------------------------------------------------------------------------
def plaza(shape, surface):
    """`FillPlaza Fill_Areas_Uniformly` (PointExtents 150, a 300 cm cell) on the UNALIGNED input shape, then
    `Subgraph_29` onto the terrain. Each tile carries `Asset` = SM_Plaza_Square_A, the mesh `SpawnPlaza`
    reads (`UseMeshAttribute`, `MeshAttribute` Asset; its `Assets` override is the same mesh). 1871 tiles
    on the demo shape."""
    if len(shape) < 3:
        return Points()
    locs, yaw = G.fill_uniform([(p[0], p[1]) for p in shape], shape[0][2], PLAZA_EXTENT_CM)
    pts = Points()
    pts.declare(AS.ASSET_ATTR, "SoftObjectPath")
    e = PLAZA_EXTENT_CM
    for p in locs:
        pts.add(p, rot=(0.0, yaw, 0.0), bounds_min=(-e, -e, -e), bounds_max=(e, e, e), steepness=1.0,
                **{AS.ASSET_ATTR: PLAZA_MESH})
    return project(pts, surface)


def tower(inputs, params, ops, rng=None, loader=None):
    """The whole computation upstream of the first native node; returns ({pin: [value]}, notes)."""
    out = {pin: [] for pin in OUTPUTS}
    shape = shape_of(inputs)
    if not shape:
        return out, ["no input shape: nothing"]
    surface = _surface(inputs)
    pivot = pivot_of(inputs)
    base = aligned(shape)
    outer = outer_ring(base, ops)
    inner = inner_ring(base, shape, ops, surface)
    sectors = arms(outer, shape, pivot, ops)
    hexes = hexagons(inner)
    samples, tz = tree_samples(shape, ops)
    bases, upright = trees(samples, tz, bool(params["UseMegaplantsTrees"]), surface, rng, loader)
    tiles = plaza(shape, surface)
    out["InnerRing"] = [inner] if inner else []
    out["Hexagons"] = hexes
    for pin in ("Sector90", "Sector80", "Sector70"):
        out[pin] = [sectors[pin]] if sectors[pin] else []
    out["TreeBases"], out["Trees"] = bases, upright
    out["PlazaTiles"] = [tiles] if len(tiles) else []
    notes = ["shape %d points; outer %d, inner %d (z %.4f); pivot %s" % (
        len(shape), len(outer), len(inner), inner[0][2] if inner else 0.0, pivot),
        "sectors %s; hexagons %d; tree samples %d; plaza %d" % (
            [len(sectors[p]) for p in ("Sector90", "Sector80", "Sector70")], len(hexes), len(samples), len(tiles)),
        "UseMegaplantsTrees=%s" % bool(params["UseMegaplantsTrees"])]
    if pivot is None:
        notes.append("no Self point: the arm chain has no frame to turn about, so no sectors")
    if loader is None:
        notes.append("no asset loader (ctx.ops.assets): no trees assigned")
    return out, notes


def _spline(ring):
    return Spline([tuple(p) for p in ring], closed=True, linear=True)


def tagged(raw):
    out = {pin: [] for pin in OUTPUTS}
    for pin in ("InnerRing", "Sector90", "Sector80", "Sector70"):
        out[pin] = [(_spline(r), [pin]) for r in raw[pin] if r]
    out["Hexagons"] = [(_spline(h), ["Hexagons"]) for h in raw["Hexagons"]]
    for pin in ("TreeBases", "Trees", "PlazaTiles"):
        out[pin] = [(pts, [pin]) for pts in raw[pin] if isinstance(pts, Points) and len(pts)]
    return out


def run(inputs, params, ctx):
    raw, notes = tower(inputs, params, ctx.ops, ctx.rng, getattr(ctx.ops, "assets", None))
    ctx.notes += notes
    return tagged(raw)
