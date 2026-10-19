"""Stage 14 -- Parkings (PCG_3_2_3_Parkings, 停车场).

The plaza-side reserved lots stage 13 published become parking lots: a band of spaces round the edge,
rows of spaces back to back inside, an aisle down each row pair, arrows on the medians, ground tiles,
parked cars, a concrete-barrier grammar and a chain-link-fence grammar. The official graph is 81 nodes
(68 of them computation); `docs/pypcg/stages/s14.md` names the official node behind every step.

This node is everything BEFORE the two kept grammar nodes; `s14_parkings_finish` is everything after them.

The chain (official node names in brackets):

  OUTER      each lot contracted 300 cm [Subgraph_29], cut at its corners [Subgraph_36 Extract_Segments, 2 deg],
             500 cm off both ends (reversed) [Subgraph_43 Transform_Truncate], the chord [Subgraph_44
             Transform_Resample NumberOfSamples], less the median bands [Subgraph_61 Compose_Spline_Cut], a
             point every 350 cm fitted [Subgraph_62 Transform_Resample]
  INNER      the outer area contracted 800 cm [Subgraph_33], a 19 x 45 m grid [Subgraph_32
             Subdivide_Areas_withGrid], each cell contracted 500 cm [Subgraph_30], its centre line
             [Subgraph_35, subdivision (1, 2)] -> `CentralLines`; a point every 350 cm fitted [Subgraph_45], the
             two rows +-300 cm to the side [Subgraph_46 / 47 Transform_Offset]
  SPACES     every segment of the two rows and of the outer lines [Subgraph_38 Extract_Segments, 0 deg],
             its centre [Subgraph_40 Place_Point_AtCenter]; the rows' and outer lines' control points
             [Subgraph_52 Place_OnSpline] -> one parking line decal each [Subgraph_7 Assign_Assets]
  CARS       80 % of the spaces occupied [Subgraph_48 Filter_RandomChoice, per point], half of those
             reversed [Subgraph_49]: a car each, yaw +90 [Subgraph_4] or -90 and +-50 cm [Subgraph_5]
  MEDIANS    each lot grown 200 cm [Subgraph_56], its two middle lines [Subgraph_55, subdivision (2, 2)];
             their 8 m bands [Subgraph_57 Transform_Outline] cut the outer lines and the border;
             600 cm off both ends [Subgraph_63], (-100, +200) and (+100, -200) to the side [Subgraph_66 / 67],
             the second reversed [Subgraph_68], an arrow at every control point [Subgraph_65
             Place_OnSpline, inward; Subgraph_8 Assign_Assets]
  BORDER     each lot cut at its corners [Subgraph_59, 2 deg], every segment in six [Subgraph_58
             Transform_Resample, Subdivision 5], less the median bands [Subgraph_60] -> `Border`
  TILES      each lot on a 2 m grid [Subgraph_10 Fill_Areas_Uniformly, SM_Lane_Car_200_200], -19 cm
             [Subgraph_11]

`CentralLines` and `Border` go to the kept `Subgraph_53 Assign Concrete Barrier Grammar`, `Border` to the kept
`Subgraph_54 Assign Chain-Link Fence Grammar`; the points to `s14_parkings_finish` with the grammars' output.
"""
from pypcg import geo
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.geo import roads as R
from pypcg.geo import sections as SEC
from pypcg.geo import splines as SP

STAGE = 14
DOC = """Parkings (停车场): the lots stage 13 published become parking lots -- an outer band of spaces, back to
back rows inside with an aisle down each, arrows on the two medians, 2 m ground tiles, cars on 80 % of the
spaces (half of them reversed), concrete barriers on the aisles and the border, a chain-link fence on the
border less its entrances."""
RANDOM = True
PARAMS = {}
INPUTS = {"ParkingFootprint": "area"}
OUTPUTS = ("CentralLines", "Border", "Lines", "Tiles", "Arrows", "ForwardCars", "ReverseCars")

# ---- the graph's fixed settings (instance overrides; anything not listed is the primitive default) ----
OUTER_CONTRACT_CM = 300.0          # Subgraph_29 Contract (UnionBeforeOutputting: the default, true)
INNER_CONTRACT_CM = 800.0          # Subgraph_33
GRID_WIDTH_CM, GRID_LENGTH_CM = 1900.0, 4500.0   # Subgraph_32 GridWidth / GridLength (size mode)
GRID_EXTEND_CM = 100000.0          # the grid loop's Extend_open_Spline_segment_each_side
AISLE_CONTRACT_CM = 500.0          # Subgraph_30
CENTRAL_SUBDIV = (1, 2)            # Subgraph_35 SubdivWidth / SubdivLength, UseSubdivisionInsteadOfSizes
MEDIAN_EXPAND_CM = 200.0           # Subgraph_56 Expand (UnionBeforeOutputting: the default, false)
MEDIAN_SUBDIV = (2, 2)             # Subgraph_55
MEDIAN_WIDTH_CM = 800.0            # Subgraph_57 Transform_Outline Width
CUT_ANGLE_DEG = 2.0                # Subgraph_36 / 59 CutAngleThreshold
OUTER_TRUNC_CM = 500.0             # Subgraph_43 Start/EndOffset
MEDIAN_TRUNC_CM = 600.0            # Subgraph_63
SPACE_CM = 350.0                   # Subgraph_45 / 62 Distance, FitToCurve
ROW_OFFSET_CM = 300.0              # Subgraph_46 / 47 offset Y
BORDER_SUBDIV = 5                  # Subgraph_58 Subdivision
ARROW_OFFSETS = ((-100.0, 200.0), (100.0, -200.0))   # Subgraph_66 / 67 offset (X, Y)
ARROW_YAW = 90.0                   # Subgraph_65 Facing "inward": TransformPoints_1, yaw +90
OCCUPANCY = 0.8                    # Subgraph_48 Ratio (RandomPerDataset false: one draw per space)
REVERSED = 0.5                     # Subgraph_49 Ratio
TILE_EXTENT = (100.0, 100.0, 10.0)  # Subgraph_10: SM_Lane_Car_200_200's bounds (BoundsFromMesh)
TILE_LIFT_CM = -19.0               # Subgraph_11 offset Z
TILE_MESH = "/CitySamplePCG/Meshes/Roads/SM_Lane_Car_200_200.SM_Lane_Car_200_200"
LINE_MESH = "/CitySamplePCG/Meshes/Roads/SM_Yellow_Line_Parking_inst.SM_Yellow_Line_Parking_inst"
ARROW_MESH = "/Game/Road/Kit_MeshDecals_A/Mesh/SM_mesh_decal_arrow_head.SM_mesh_decal_arrow_head"
_VEH = "/Game/Vehicle/%s/Mesh/SM_%s.SM_%s"
CARS = tuple(_VEH % (k, k, k) for k in ("vehCar_vehicle02", "vehCar_vehicle03", "vehCar_vehicle05",
                                        "vehCar_vehicle06", "vehCar_vehicle07", "vehVan_vehicle01",
                                        "vehTruck_vehicle04"))           # Subgraph_4 / 5 Assets
# Subgraph_7 / 8 / 4 / 5 overrides, in the keys `geo.assets.expand_items` reads
LINE_SETTINGS = {"position_offset": {"X": 0, "Y": 0, "Z": 3}, "rotation_offset": {"Pitch": 0, "Yaw": 0, "Roll": 0},
                 "scale_offset": {"X": 1, "Y": 1, "Z": 1}, "extents_scale": {"X": 1.2, "Y": 1, "Z": 1},
                 "uniform_scale": False, "use_mesh_bounds": False}
ARROW_SETTINGS = {"position_offset": {"X": 0, "Y": 0, "Z": 40}}
FORWARD_SETTINGS = {"rotation_offset": {"Pitch": 0, "Yaw": 90, "Roll": 0},
                    "random_rotation_range": {"X": 0, "Y": 0, "Z": 5}}
REVERSE_SETTINGS = {"rotation_offset": {"Pitch": 0, "Yaw": -90, "Roll": 0},
                    "random_position_range": {"X": 0, "Y": 50, "Z": 0},
                    "random_rotation_range": {"X": 0, "Y": 0, "Z": 5}}


class Draws:
    """Every random choice of the stage, in one place, so a check can replace one kind with the official
    outcome and replay the rest (stage 9's design). `keep(step, n, ratio)` is a `Filter_RandomChoice` with
    `RandomPerDataset` false: one Bernoulli per POINT (`geo.keep_each`); `rng` the car picks and their
    random ranges."""

    def __init__(self, rng):
        self.rng = rng

    def keep(self, step, n, ratio):
        return geo.keep_each(n, ratio, self.rng)


# ---- areas -----------------------------------------------------------------------------------------
def lots_of(inputs):
    return A.areas_of(inputs.get("ParkingFootprint", []))


def outer_areas(lots, ops):
    """`Subgraph_29`: every lot contracted 300 cm, the results united (the primitive's default), in the
    order and from the start vertex the engine gives them (`geo.areas.follow_subjects`)."""
    return A.follow_subjects(A.contract(lots, OUTER_CONTRACT_CM, ops), lots)


def inner_areas(outer, ops):
    """`Subgraph_33`: the outer areas contracted 800 cm, united. The start vertex matters here: the grid
    below is laid from the ring's first longest edge, and the two long sides of a rectangle tie."""
    return A.follow_subjects(A.contract(outer, INNER_CONTRACT_CM, ops), outer)


def grid_cells(inner, ops):
    """`Subgraph_32 Subdivide_Areas_withGrid` (size mode, 19 x 45 m): the cells, each a polygon."""
    cells = []
    for p in inner:
        full = [seg for _a, seg in geo.grid_lines(p.outer, GRID_WIDTH_CM, GRID_LENGTH_CM, GRID_EXTEND_CM,
                                                   clipped=False)]
        cells += [Polygon(r) for r in ops.cut_with_paths(p.outer, full)] if full else [p]
    return cells


def middle_lines(areas, subdiv):
    """`Subdivide_Areas_withGrid` in subdivision mode, its `Subdividing_splines`: the clipped lines of
    each area, X lines then Y lines, as paths. The official lines run the other way from
    `geo.grid_lines`' (measured: all 36 central lines and all 10 medians), so each is reversed here; the
    direction decides which row is A and which is B, the decals' yaw, and the arrows' sides."""
    out = []
    for p in areas:
        for _axis, seg in geo.grid_lines(p.outer, 0.0, 0.0, GRID_EXTEND_CM, subdiv):
            path = [SP._xyz(q) for q in reversed(seg)]
            if len(path) >= 2 and SP.length(path) > 0.0:
                out.append(path)
    return out


def aisles(cells, ops):
    """`Subgraph_30`: every cell contracted 500 cm, united."""
    return A.follow_subjects(A.contract(cells, AISLE_CONTRACT_CM, ops), cells)


def central_lines(aisle_areas):
    """`Subgraph_35`: the centre line of every aisle (subdivision (1, 2): one line down its length)."""
    return middle_lines(aisle_areas, CENTRAL_SUBDIV)


def medians(lots, ops):
    """`Subgraph_56` (each lot grown 200 cm, no union) then `Subgraph_55` (its two middle lines)."""
    return middle_lines(A.follow_subjects(A.expand(lots, MEDIAN_EXPAND_CM, ops), lots), MEDIAN_SUBDIV)


def median_bands(lines, ops):
    """`Subgraph_57 Transform_Outline` (8 m): the band round every median line."""
    out = []
    for path in lines:
        out += R.outline([tuple(q[:2]) for q in path], MEDIAN_WIDTH_CM, ops)
    return out


def _runs(polys):
    """`Extract_Segments (2 deg)` on every polygon's outer ring: its straight runs, in ring order."""
    out = []
    for p in polys:
        ring = [SP._xyz(q) for q in p.outer]
        out += [list(r) for r in geo.extract_segments(ring, CUT_ANGLE_DEG)]
    return out


def _cut(paths, bands, ops):
    """`Compose_Spline_Cut` (Difference): the parts of each path outside every band."""
    rings = [b.outer for b in bands]
    return SEC.cut_paths(paths, rings, ops, inside=False) if rings else [list(p) for p in paths]


# ---- lines -------------------------------------------------------------------------------------------
def outer_lines(outer, bands, ops):
    """`Subgraph_36` -> `43` -> `44` -> `61` -> `62`: the outer band's space lines."""
    runs = [SP.chord(SP.truncate(r, OUTER_TRUNC_CM, OUTER_TRUNC_CM)) for r in _runs(outer)]
    cut = _cut(runs, bands, ops)
    return [x for x in (SP.resample_fit(p, SPACE_CM) for p in cut) if x]


def inner_rows(central):
    """`Subgraph_45` -> `46` / `47`: (row A, row B) -- the centre lines resampled every 350 cm, then +-300 cm."""
    res = [x for x in (SP.resample_fit(p, SPACE_CM) for p in central) if x]
    return ([SP.offset_local(p, 0.0, ROW_OFFSET_CM) for p in res],
            [SP.offset_local(p, 0.0, -ROW_OFFSET_CM) for p in res])


def border(lots, bands, ops):
    """`Subgraph_59` -> `58` -> `60`: the lot border in runs, every segment in six, less the median bands."""
    return _cut([SP.subdivide(r, BORDER_SUBDIV) for r in _runs(lots)], bands, ops)


def arrow_lines(median_lines):
    """`Subgraph_63` -> `66` / `67` -> `68`: (side A, side B reversed)."""
    trunc = [SP.truncate(p, MEDIAN_TRUNC_CM, MEDIAN_TRUNC_CM) for p in median_lines]
    side_a = [SP.offset_local(p, *ARROW_OFFSETS[0]) for p in trunc]
    side_b = [list(reversed(SP.offset_local(p, *ARROW_OFFSETS[1]))) for p in trunc]
    return side_a, side_b


# ---- points ------------------------------------------------------------------------------------------
def control_points(path, yaw_offset=0.0):
    """`Place_OnSpline (UseExistingControlPoints)`: the path's control points, each turned along the path
    (`Facing` tangent; inward adds yaw +90), box +-1, steepness 1 (`GetSplineControlPoints`)."""
    pts = Points()
    for p, yaw in zip(path, SP.control_yaws(path)):
        pts.add(p, rot=(0.0, yaw + yaw_offset, 0.0), steepness=1.0)
    return pts


def space_centres(paths):
    """`Subgraph_38` (every segment) then `Subgraph_40 Place_Point_AtCenter`: one point per space, box
    +-100 cm, steepness 1, in the paths' order."""
    pts = Points()
    for path in paths:
        for run in SP.pairs(path):
            loc, yaw = SP.center(run)
            pts.add(loc, rot=(0.0, yaw, 0.0), bounds_min=(-100.0, -100.0, -100.0),
                    bounds_max=(100.0, 100.0, 100.0), steepness=1.0)
    return pts


def tile_points(lot):
    """`Subgraph_10 Fill_Areas_Uniformly` (the mesh's extents: a 2 m grid) then `Subgraph_11` (-19 cm)."""
    locs, yaw = G.fill_uniform(lot.outer, lot.z, TILE_EXTENT[0])
    pts = Points()
    pts.declare(AS.ASSET_ATTR, "SoftObjectPath")
    lo, hi = tuple(-e for e in TILE_EXTENT), TILE_EXTENT
    for p in locs:
        pts.add((p[0], p[1], p[2] + TILE_LIFT_CM), rot=(0.0, yaw, 0.0), bounds_min=lo, bounds_max=hi,
                steepness=1.0, **{AS.ASSET_ATTR: TILE_MESH})
    return pts


def _merged(sets):
    """`Assign_Assets` merges its input items, `$Seed += dataIndex`."""
    out = Points()
    for k, s in enumerate(sets):
        for j in range(len(s)):
            out.add(s.loc[j], rot=s.rot[j], scale=s.scale[j], density=s.density[j], bounds_min=s.bounds_min[j],
                    bounds_max=s.bounds_max[j], color=s.color[j], steepness=s.steepness[j],
                    seed=AS._i32(int(s.seed[j]) + k))
    return out


def _assign(sets, path, settings, loader):
    targets = _merged(sets)
    if not len(targets) or loader is None:
        return []
    table = loader([path])
    return AS.expand_items(targets, table, [0] * len(targets), dict(settings))


def cars(spaces, draws, loader):
    """`Subgraph_48` / `49` then `Subgraph_4` / `5`: (forward items, reverse items)."""
    occ = draws.keep("occupancy", len(spaces), OCCUPANCY)
    taken = spaces.take([i for i, f in enumerate(occ) if f])
    rev = draws.keep("reversed", len(taken), REVERSED)
    fwd_pts = taken.take([i for i, f in enumerate(rev) if f])
    rev_pts = taken.take([i for i, f in enumerate(rev) if not f])
    out = []
    for pts, settings in ((fwd_pts, FORWARD_SETTINGS), (rev_pts, REVERSE_SETTINGS)):
        if not len(pts) or loader is None:
            out.append([])
            continue
        table = loader(list(CARS))
        picks = AS.choose(len(pts), CARS, draws.rng)
        out.append(AS.expand_items(pts, table, picks, dict(settings, rng=draws.rng)))
    return out[0], out[1], len(taken)


def parkings(inputs, ops, draws, loader=None):
    """The whole computation; returns ({pin: [value]}, notes)."""
    out = {pin: [] for pin in OUTPUTS}
    lots = lots_of(inputs)
    if not lots:
        return out, ["no parking footprint"]
    outer = outer_areas(lots, ops)
    cells = grid_cells(inner_areas(outer, ops), ops)
    central = central_lines(aisles(cells, ops))
    med = medians(lots, ops)
    bands = median_bands(med, ops)
    outer_res = outer_lines(outer, bands, ops)
    row_a, row_b = inner_rows(central)
    rows = row_a + row_b + outer_res                       # Subgraph_38 / 52 input order: 46, 47, 62
    spaces = space_centres(rows)
    line_sets = [control_points(p) for p in rows]
    side_a, side_b = arrow_lines(med)
    arrow_sets = [control_points(p, ARROW_YAW) for p in side_a + side_b]
    out["CentralLines"] = central
    out["Border"] = border(lots, bands, ops)
    out["Lines"] = _assign(line_sets, LINE_MESH, LINE_SETTINGS, loader)
    out["Arrows"] = _assign(arrow_sets, ARROW_MESH, ARROW_SETTINGS, loader)
    out["Tiles"] = [t for t in (tile_points(p) for p in lots) if len(t)]
    fwd, rev, taken = cars(spaces, draws, loader)
    out["ForwardCars"], out["ReverseCars"] = fwd, rev
    notes = ["%d lots: %d outer lines, %d cells, %d central lines, %d medians, %d border runs"
             % (len(lots), len(outer_res), len(cells), len(central), len(med), len(out["Border"])),
             "%d spaces, %d line points, %d occupied (%d forward, %d reversed), %d arrows, %d tiles"
             % (len(spaces), sum(len(s) for s in line_sets), taken, sum(len(x) for x in fwd[-1:]),
                sum(len(x) for x in rev[-1:]), sum(len(s) for s in arrow_sets), sum(len(t) for t in out["Tiles"]))]
    return out, notes


def _spline(path):
    return Spline([tuple(p) for p in path], closed=False, linear=True,
                  rotations=[(0.0, y, 0.0) for y in SP.control_yaws(path)])


def tagged(raw):
    out = {pin: [] for pin in OUTPUTS}
    out["CentralLines"] = [(_spline(p), ["CentralLines"]) for p in raw["CentralLines"]]
    out["Border"] = [(_spline(p), ["Border"]) for p in raw["Border"]]
    for pin in ("Lines", "Tiles", "Arrows", "ForwardCars", "ReverseCars"):
        out[pin] = [(pts, [pin]) for pts in raw[pin] if len(pts)]
    return out


def run(inputs, params, ctx):
    loader = getattr(ctx.ops, "assets", None)
    raw, notes = parkings(inputs, ctx.ops, Draws(ctx.rng), loader)
    ctx.notes += notes
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): no lines, arrows or cars assigned")
    return tagged(raw)
