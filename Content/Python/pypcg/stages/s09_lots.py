"""Stage 9 -- Lots (PCG_3_1_4_Lots, 地块).

Cuts the city into lots and the lots into building footprints. The official graph is 183 nodes, 135
of them computation; counting the 56 primitive calls' own graphs (six `Subdivide_Areas_WithRecursiveSplit`
at 171 nodes each with `AutoSplitPolygon` and its loops, `Subdivide_Areas_withGrid` 169, ten
`Filter_Areas_BySize` 29, eleven `Compose_Areas_Exclusion` 27, ...) the surface is about 2 600 nodes,
4 400 with each primitive's shared input / output templates. `docs/pypcg/stages/s09.md` names the
official node behind every step and the table of counts.

The chain, top to bottom (official node names in brackets):

  1. LOTS        City - RoadFootprints [Subgraph_0], - CentralParkFootprint, MainTower [Subgraph_20]
                 -> published as `Lots` [Subgraph_17]
  2. PREPARED    - UndividableDistricts [Subgraph_8], - LandmarkPark [Subgraph_24], then one draw
                 per lot [Subgraph_3 Filter_RandomChoice, Ratio = PlazaReservationRatio]: kept ->
                 "Prepared Lots", the rest -> `reservedLots` [Subgraph_16]
  3. PER CLASS   Prepared x class districts [Intersect_LotsWith*]; LARGE only: the inner grid
                 [Subgraph_57 Subdivide_Areas_withGrid, subdiv (1, 2)] whose lines go to the kept
                 road grammar [Subgraph_58] and whose 10 m road bands are carved out [Subgraph_59];
                 then lot min / max size [Subgraph_1_*, Subgraph_2_*], whose rejects are
                 `unbuildableLots` [Gather_0 -> Subgraph_14]
  4. COURTYARDS  SMALL / MEDIUM: split the lots [Subgraph_30 / 28], contract the whole lot by 20 / 30 m
                 [Subgraph_64 / 66] -> `Small Courtyards` / `Medium Courtyards` [AddTags_1 / 0], carve
                 the courtyard out of the split pieces [Subgraph_65 / 67]
  5. HIGHWAY     the pieces under the highway -> `UnderHighway` [Subgraph_7 / 6 / 2 -> AddTags_2];
                 the rest go on [Subgraph_72 / 73 / 74]
  6. FOOTPRINTS  split again [Subgraph_6_*], footprint min size [Subgraph_7_*], shortest side
                 [Subgraph_31 / 29 / 32 FilterPolygonByEdgeLength]; rejects -> `UnbuildableFootprints`
                 [Gather_3 / 2 / 4 -> Gather_1 -> Subgraph_13]
                 SMALL  -> `SmallDistrictsBldgFootprints` [WriteTag_SmallDistricts]
                 MEDIUM -> one draw each, 0.9 kept [Subgraph_75] -> `MediumDistrictsBldgFootprints`,
                           the culled ones -> `UnbuildableFootprints`
                 LARGE  -> over 2 500 m2 [Subgraph_68]: contracted 9 m [Subgraph_70] -> pads; the rest
                           as they are; both -> `LargeDistrictsBldgFootprints`; the ring between the
                           pad and its footprint, split [Subgraph_25] then less the pads
                           [Subgraph_18] -> `LargeBuildingSkirt` [Subgraph_26]
"""
from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.geo import areas as A
from pypcg.stage_api import Param

STAGE = 9
DOC = """Lots (地块): cuts the City outline (actor tag City) by the road footprint, the landmark,
the central park, the undividable districts and the small landmark park into lots; reserves a share
of them (PlazaReservationRatio is the share KEPT, one draw per lot); splits the rest per district
class into building footprints with courtyards (small, medium), an inner back-alley grid (large) and
the highway's footprint taken out. Sizes are in m2. Outputs Lots, reservedLots, unbuildableLots,
UnbuildableFootprints, Small/Medium/LargeDistrictsBldgFootprints, Small Courtyards, Medium
Courtyards, UnderHighway and LargeBuildingSkirt, plus the grid lines the kept road grammar reads."""
RANDOM = True
_F = "Float"
PARAMS = {
    "PlazaReservationRatio": Param(0.8999999761581421, "Ratio of lots reserved for buildings vs plazas: "
                                   "each lot is KEPT with this probability (one draw per lot)", type=_F),
    "BuildableLotMinSizeSmallDistrict": Param(1000.0, "Minimum lot size in small districts", type=_F),
    "BuildableLotMaxSizeSmallDistrict": Param(15000.0, "Maximum lot size in small districts", type=_F),
    "BuildableFootprintMinSizeSmallDistrict": Param(500.0, "Minimum footprint size in small districts", type=_F),
    "BuildableLotMinSizeMediumDistrict": Param(2000.0, "Minimum lot size in medium districts", type=_F),
    "BuildableLotMaxSizeMediumDistrict": Param(22000.0, "Maximum lot size in medium districts", type=_F),
    "BuildableFootprintMinSizeMediumDistrict": Param(500.0, "Minimum footprint size in medium districts", type=_F),
    "BuildableLotMinSizeLargeDistrict": Param(2000.0, "Minimum lot size in large districts", type=_F),
    "BuildableLotMaxSizeLargeDistrict": Param(48000.0, "Maximum lot size in large districts", type=_F),
    "BuildableFootprintMinSizeLargeDistrict": Param(1500.0, "Minimum footprint size in large districts", type=_F),
}
INPUTS = {"City": "spline", "Districts": "area", "RoadFootprints": "polygon", "MainTower": "polygon",
          "CentralParkFootprint": "polygon", "LandmarkPark": "polygon", "Highway": "polygon"}
OUTPUTS = ("Lots", "ReservedLots", "UnbuildableLots", "UnbuildableFootprints", "SmallFootprints",
           "MediumFootprints", "LargeFootprints", "SmallCourtyards", "MediumCourtyards", "UnderHighway",
           "LargeBuildingSkirt", "GridSplines")
# pin -> the contract tag its items carry (the official Write_Tag / AddTags value)
TAGS = {"Lots": "Lots", "ReservedLots": "reservedLots", "UnbuildableLots": "unbuildableLots",
        "UnbuildableFootprints": "UnbuildableFootprints", "SmallFootprints": "SmallDistrictsBldgFootprints",
        "MediumFootprints": "MediumDistrictsBldgFootprints", "LargeFootprints": "LargeDistrictsBldgFootprints",
        "SmallCourtyards": "Small Courtyards", "MediumCourtyards": "Medium Courtyards",
        "UnderHighway": "UnderHighway", "LargeBuildingSkirt": "LargeBuildingSkirt"}
# `GridSplines` is the one output that is not a contract output: the large lots' inner grid
# (`Subgraph_57.Subdividing_splines`), which only the kept `Subgraph_58` road grammar reads.
INTERNAL = ("GridSplines",)
CLASSES = ("Small", "Medium", "Large")

# ---- the graph's fixed settings (instance overrides; anything not listed is the primitive default) ----
# Subdivide_Areas_WithRecursiveSplit defaults: Iterations 2, MaxSplitDistancFromCenter 0.3, MinAreaSize 1000.
LOT_SPLIT = {"Small": (2, 0.1, 1000.0),          # Subgraph_30
             "Medium": (2, 0.1, 1000.0)}         # Subgraph_28
COURTYARD_CM = {"Small": 2000.0, "Medium": 3000.0}            # Subgraph_64 / 66 Contract
FOOTPRINT_SPLIT = {"Small": (3, 0.3, 1000.0),    # Subgraph_6_SmallDistrict
                   "Medium": (1, 0.3, 1500.0),   # Subgraph_6_MediumDistrict
                   "Large": (2, 0.2, 2000.0)}    # Subgraph_6_LargeDistrict
SIDE_MIN_CM = {"Small": 300.0, "Medium": 600.0, "Large": 400.0}  # Subgraph_31 / 29 / 32 Threshold, Greater
MEDIUM_KEEP = 0.9                                # Subgraph_75 Ratio (RandomPerDataset, the default)
LARGE_PAD_MIN_M2 = 2500.0                        # Subgraph_68 Greater 2500
LARGE_PAD_CONTRACT_CM = 900.0                    # Subgraph_70
SKIRT_SPLIT = (2, 0.05, 300.0)                   # Subgraph_25
GRID_SUBDIV = (1, 2)                             # Subgraph_57: SubdivWidth default 1, SubdivLength 2
GRID_EXTEND_CM = 100000.0                        # the loop's Extend_open_Spline_segment_each_side
GRAMMAR_WIDTH_CM = 1000.0                        # Subgraph_58 Size: the band CreatePolygon2D(ForceOpen) closes


class Draws:
    """Every random choice of the stage, in one place, so a check can replace one kind of draw with the
    official outcome and replay the rest. `keep(step, n, ratio)` is a `Filter_RandomChoice`
    (`geo.keep_each`); `ratio(step, max_from_center)` gives an `AutoSplitPolygon` split ratio
    function, uniform in [0.5 - c, 0.5 + c] with c clamped to [0.05, 0.45] as the CoreProcess does."""

    def __init__(self, rng):
        self.rng = rng

    def keep(self, step, items, ratio):
        return geo.keep_each(len(items), ratio, self.rng)

    def ratio(self, step, max_from_center):
        c = min(max(float(max_from_center), 0.05), 0.45)
        rng = self.rng
        return lambda ring: 0.5 - c + 2.0 * c * rng.random()


# ---- inputs -------------------------------------------------------------------------------------
def _ring(v):
    """A closed area as a ring: a Polygon's outer, a CLOSED spline's polyline (`CreatePolygon2D
    ForceClosed`, 1 cm discretisation, which is what `convert` reads the polyline with). An open
    spline is no area: `Compose_Shared_InputsProcessing` forwards it and the CoreProcess filters it
    out."""
    if isinstance(v, Polygon):
        return v
    if isinstance(v, Spline) and v.closed:
        r = geo.drop_closing(geo.xy(v.polyline or v.points))
        return Polygon(geo.ccw(r)) if len(r) >= 3 else None
    return None


def areas_of(items, tag=None):
    out = []
    for v, tags in items:
        if tag is not None and tag not in tags:
            continue
        p = _ring(v)
        if p is not None:
            out.append(p)
    return out


def _split(pieces, spec, ops, draws, step):
    iterations, from_center, min_m2 = spec
    fn = draws.ratio(step, from_center)
    out = []
    for p in pieces:
        geo.recursive_split(p.outer, ops, iterations, min_m2 * 1e4, fn, out, [])
    return [Polygon(r) for r in out]


def _pick(items, flags):
    return [p for p, f in zip(items, flags) if f], [p for p, f in zip(items, flags) if not f]


def grid(lots, ops):
    """`Subgraph_57 Subdivide_Areas_withGrid` (subdivision mode, (1, 2)) on each large lot:
    (areas, the clipped lines). The areas are `CutWithPaths` of the lot by the whole grid lines."""
    areas, lines = [], []
    for p in lots:
        full = [seg for _a, seg in geo.grid_lines(p.outer, 0.0, 0.0, GRID_EXTEND_CM, GRID_SUBDIV, clipped=False)]
        lines += [seg for _a, seg in geo.grid_lines(p.outer, 0.0, 0.0, GRID_EXTEND_CM, GRID_SUBDIV)]
        areas += [Polygon(r) for r in ops.cut_with_paths(p.outer, full)] if full else [p]
    return areas, lines


def grammar_bands(lines, ops):
    """The kept road grammar's `Footprints` for straight grid lines: `Assign_ShapeGrammarDefinition_
    CoreProcess` takes its `Branch_0 Output B` side for this SGD (`Orientation = Horizontal`, probed
    2026-10-19), i.e. `CleanSpline_1` -> `CreatePolygon2D_1 (ForceOpen, Butt, width = Size)`. A
    two-point line is untouched by the clean, so the band is `path_offset(line, Size)` -- the FULL
    width, which Clipper halves for an open path."""
    out = []
    for seg in lines:
        if len(seg) >= 2:
            out += ops.path_offset([tuple(q[:2]) for q in seg], GRAMMAR_WIDTH_CM, end="butt")
    return out


def lots(inputs, params, ops, draws):
    """The whole computation; returns {pin: [Polygon | path]} (no tags)."""
    out = {pin: [] for pin in OUTPUTS}
    city = areas_of(inputs.get("City", []))
    roads = areas_of(inputs.get("RoadFootprints", []))
    landmarks = areas_of(inputs.get("CentralParkFootprint", [])) + areas_of(inputs.get("MainTower", []))
    districts = inputs.get("Districts", [])
    highway = areas_of(inputs.get("Highway", []))

    # 1. Subgraph_0 (City - roads), Subgraph_20 (- the central park and the landmark) -> Lots
    lots_1 = A.exclusion(A.exclusion(city, roads, ops), landmarks, ops)
    out["Lots"] = lots_1
    if not lots_1:
        return out
    # 2. Subgraph_8 (- undividable districts), Subgraph_24 (- the small landmark park), Subgraph_3
    pieces = A.exclusion(A.exclusion(lots_1, areas_of(districts, "UndividableDistricts"), ops),
                         areas_of(inputs.get("LandmarkPark", [])), ops)
    prepared, out["ReservedLots"] = _pick(pieces, draws.keep("plaza", pieces, params["PlazaReservationRatio"]))

    unbuildable_lots, unbuildable_fp = [], []
    under = []
    for cls in CLASSES:
        inter = A.intersection(prepared, areas_of(districts, cls + "Districts"), ops) \
            if areas_of(districts, cls + "Districts") else []
        if cls == "Large":
            cells, lines = grid(inter, ops)
            out["GridSplines"] = lines
            inter = A.exclusion(cells, grammar_bands(lines, ops), ops)        # Subgraph_59
        ok, small_rej = A.by_size(inter, params["BuildableLotMinSize%sDistrict" % cls])
        ok, big_rej = A.by_size(ok, params["BuildableLotMaxSize%sDistrict" % cls], greater=False)
        unbuildable_lots += small_rej + big_rej
        if cls in COURTYARD_CM:
            split = _split(ok, LOT_SPLIT[cls], ops, draws, cls + " lots")
            yards = A.contract(ok, COURTYARD_CM[cls], ops)
            out[cls + "Courtyards"] = yards
            carved = A.exclusion(split, yards, ops)
        else:
            carved = ok
        under += A.intersection(carved, highway, ops) if highway else []
        rest = A.exclusion(carved, highway, ops)
        fps = _split(rest, FOOTPRINT_SPLIT[cls], ops, draws, cls + " footprints")
        fps, rej = A.by_size(fps, params["BuildableFootprintMinSize%sDistrict" % cls])
        fps, rej_side = A.by_edge_length(fps, SIDE_MIN_CM[cls])
        unbuildable_fp += rej + rej_side
        if cls == "Small":
            out["SmallFootprints"] = fps
        elif cls == "Medium":
            kept, culled = _pick(fps, draws.keep("medium footprints", fps, MEDIUM_KEEP))
            out["MediumFootprints"] = kept
            unbuildable_fp += culled
        else:
            big, small = A.by_size(fps, LARGE_PAD_MIN_M2)
            pads = A.contract(big, LARGE_PAD_CONTRACT_CM, ops)
            out["LargeFootprints"] = small + pads
            out["LargeBuildingSkirt"] = A.exclusion(_split(big, SKIRT_SPLIT, ops, draws, "skirt"), pads, ops)
    out["UnbuildableLots"] = unbuildable_lots
    out["UnbuildableFootprints"] = unbuildable_fp
    out["UnderHighway"] = under
    return out


def _xyz(path):
    return [(q[0], q[1], q[2] if len(q) > 2 else 0.0) for q in path]


def tagged(raw):
    out = {}
    for pin in OUTPUTS:
        if pin == "GridSplines":
            out[pin] = [(Spline(_xyz(seg), linear=True), ["GridSplines"]) for seg in raw[pin] if len(seg) >= 2]
        else:
            out[pin] = [(p, [TAGS[pin]]) for p in raw[pin]]
    return out


def run(inputs, params, ctx):
    return tagged(lots(inputs, params, ctx.ops, Draws(ctx.rng)))
