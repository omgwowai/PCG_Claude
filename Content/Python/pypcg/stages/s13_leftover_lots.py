"""Stage 13 -- LeftOverLots (PCG_3_2_2_LeftOverLots, 余地广场与植被).

What the lots stage left over becomes plazas, ground tiles and trees. The official graph is 135 nodes
(95 of them computation); `docs/pypcg/stages/s13.md` names the official node behind every step.

The chain (official node names in brackets):

  READS       the stage-9 volume's items by exact tag [Subgraph_4 reservedLots, Subgraph_5 unbuildableLots /
              UnbuildableFootprints, Subgraph_36 LargeBuildingSkirt -- the node TITLED "Only unbuildable lots",
              Subgraph_50 UnderHighway, Subgraph_29 Small Courtyards, Subgraph_18 Medium Courtyards]
  UNDIVIDABLE the undividable districts [Subgraph_7] less the central park and the landmark [Subgraph_17]
              and less every Roads area [Subgraph_8]
  SMALL PARK  the landmark's small park at z 0 [AttributeMathsOp_0] x every stage-9 item [Subgraph_58]
  SPLIT       one draw per reserved lot [Subgraph_10, Ratio_Plaza_vs_Trees, kept = plaza side]; one more
              per plaza lot [Subgraph_0, Ratio 0.3]: kept -> plazas and tiles, the rest PUBLISHED
              [Reroute_4 -> the output node]
  PLAZAS      the kept plaza lots, the under-highway lots and both courtyard classes each contracted
              322.886339 cm without a union [Subgraph_13 / 52 / 30 / 21], the building skirt as it is;
              every one lifted 30 cm [Subgraph_9 / 54 / 32 / 25 / 37] -> the five kept fitting-asset nodes
              [Subgraph_2 / 53 / 31 / 23 / 38]
  TILES       the kept plaza lots on a 3 m grid [Subgraph_34 Fill_Areas_Uniformly], +15 cm [Subgraph_48],
              fitted to the terrain [Subgraph_49], seven ways, one draw per lot [Subgraph_59..64], one plaza
              tile mesh per way [Subgraph_65..71] -> `GroundTiles` -> the kept `Subgraph_72`
  TREES       the tree-side reserved lots, the unbuildable lots and the cleaned undividable districts, each
              less the highway [Subgraph_24], with the small park: 0.02 points / m2 [Subgraph_1
              Fill_Areas_Randomly], fitted to the terrain [Subgraph_19] -> `TreePoints` -> the two native
              texture writes [Subgraph_27 / 28] -> `s13_leftover_trees` -> the kept `Subgraph_76`
"""
from pypcg import geo
from pypcg.geo import Points, Polygon
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stage_api import Param

STAGE = 13
DOC = """LeftOverLots (余地广场与植被): the reserved lots split by one draw each into a plaza side
(Ratio_Plaza_vs_Trees) and a tree side; three in ten plaza lots get plazas and ground tiles, the rest are
published for the parking stage. The under-highway lots, both courtyard classes and the large-building skirt
get fitted plazas; the tree side, the unbuildable lots, the undividable districts (less the highway) and the
small landmark park get scattered trees on the final mesh terrain, their species and scale from a texture."""
RANDOM = True
PARAMS = {
    "Ratio_Plaza_vs_Trees": Param(0.5, "Share of the reserved lots kept for plazas (one draw per lot); "
                                  "the rest are planted with trees", type="Double"),
}
INPUTS = {"Lots": "area", "Districts": "area", "Roads": "any", "Highways": "polygon", "MainTower": "polygon",
          "CentralParkFootprint": "polygon", "LandmarkPark": "spline", "MeshTerrain": "surface"}
OUTPUTS = ("PlazaLots", "ReservedPlazaAreas", "UnderHighwayAreas", "SmallCourtyardAreas", "MediumCourtyardAreas",
           "SkirtAreas", "GroundTiles", "TreePoints")

# ---- the graph's fixed settings (instance overrides; anything not listed is the primitive default) ----
PLAZA_CULL_RATIO = 0.3                 # Subgraph_0 Ratio (RandomPerDataset: the primitive default)
PLAZA_SETBACK_CM = 322.886339          # Subgraph_13 / 52 / 30 / 21 Contract, UnionBeforeOutputting false
PLAZA_LIFT_CM = 30.0                   # Subgraph_9 / 54 / 32 / 25 / 37 offset Z
TILE_EXTENT_CM = 150.0                 # Subgraph_34 PointExtents: a 3 m cell
TILE_LIFT_CM = 15.0                    # Subgraph_48 offset Z
TREES_PER_M2 = 0.02                    # Subgraph_1 PointsPerSquaredMeter
TREE_EXTENT_CM = 10.0                  # Fill_Areas_Randomly's OutputPointsExtents (default)
# Subgraph_59..64 (`Ratio`, RandomPerDataset): the literal values the official nodes carry
TILE_RATIOS = (0.142857, 0.166667, 0.2, 0.25, 0.333333, 0.5)
_MESH = "/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_%s.SM_Plaza_Square_%s"
TILE_CALLS = tuple((k, _MESH % (k, k)) for k in "ABCDEFG")     # Subgraph_65..71, Gather_1's order
TILE_OFFSET = (-150.0, -150.0, 0.0)

# The exact-tag reads of the stage-9 volume (Filter_Tags: FilterDataByTag, a comma list = any of them)
READS = {"reserved": ("reservedLots",),                                     # Subgraph_4
         "unbuildable": ("unbuildableLots", "UnbuildableFootprints"),       # Subgraph_5
         "skirt": ("LargeBuildingSkirt",),                                  # Subgraph_36 ("Only unbuildable lots")
         "under": ("UnderHighway",),                                        # Subgraph_50
         "small_yards": ("Small Courtyards",),                              # Subgraph_29
         "medium_yards": ("Medium Courtyards",)}                            # Subgraph_18


class Draws:
    """Every random choice of the stage, in one place, so a check can replace one kind with the official
    outcome and replay the rest (stage 9's design). `keep(step, items, ratio)` is a `Filter_RandomChoice`
    (`RandomPerDataset`: one Bernoulli per item, `geo.keep_each`); `ways(n)` the tiles' seven-way chain;
    `rng` everything else (the tree scatter)."""

    def __init__(self, rng):
        self.rng = rng

    def keep(self, step, items, ratio):
        return geo.keep_each(len(items), ratio, self.rng)

    def ways(self, n):
        return G.split_ways(n, TILE_RATIOS, self.rng)


def _pick(items, flags):
    return [p for p, f in zip(items, flags) if f], [p for p, f in zip(items, flags) if not f]


def _tagged(items, tags):
    out = []
    for v, t in items:
        if any(x in t for x in tags):
            p = A.area_of(v)
            if p is not None:
                out.append(p)
    return out


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def read(inputs):
    lots = inputs.get("Lots", [])
    src = {k: _tagged(lots, tags) for k, tags in READS.items()}
    src["all_lots"] = A.areas_of(lots)
    src["undividable"] = A.areas_of(inputs.get("Districts", []), "UndividableDistricts")
    src["roads"] = A.areas_of(inputs.get("Roads", []))
    src["highway"] = A.areas_of(inputs.get("Highways", []))
    src["tower"] = A.areas_of(inputs.get("MainTower", []))
    src["park"] = A.areas_of(inputs.get("CentralParkFootprint", []))
    src["small_park"] = [Polygon(p.outer, p.holes, 0.0) for p in A.areas_of(inputs.get("LandmarkPark", []))]
    return src


# ---- areas -----------------------------------------------------------------------------------------
def undividable(src, ops):
    """`Subgraph_17` (less the central park and the landmark) then `Subgraph_8` (less every Roads area)."""
    return A.exclusion(A.exclusion(src["undividable"], src["park"] + src["tower"], ops), src["roads"], ops)


def small_park(src, ops):
    """`AttributeMathsOp_0` sets the park spline's control points to z 0; `Subgraph_58` intersects it with
    every stage-9 item. An empty clip passes the park through, as the engine's intersection does."""
    return A.intersection(src["small_park"], src["all_lots"], ops)


def setback(polys, ops):
    """`Transform_Areas_Contract` (322.886339 cm, `UnionBeforeOutputting` false) then `Transform_Offset`
    (+30 cm on the polygon's control points), in the polygon's own frame (trap 64: the start vertex)."""
    out = []
    for p in polys:
        out += A.in_frame(p, lambda q: A.contract([q], PLAZA_SETBACK_CM, ops, union=False))
    return [lift(p, PLAZA_LIFT_CM) for p in out]


def lift(p, dz):
    return Polygon(list(p.outer), [list(h) for h in p.holes], p.z + dz)


def split(src, params, draws):
    """`Subgraph_10` then `Subgraph_0`: (plaza lots kept, plaza lots published, tree-side lots)."""
    plaza, trees = _pick(src["reserved"], draws.keep("plaza", src["reserved"], params["Ratio_Plaza_vs_Trees"]))
    kept, published = _pick(plaza, draws.keep("cull", plaza, PLAZA_CULL_RATIO))
    return kept, published, trees


# ---- points ----------------------------------------------------------------------------------------
def project(pts, surface):
    """`Custom_Projector_with_rotation_fix` on every point (in place); no surface -> nothing (stage 10)."""
    if surface is None:
        return Points()
    for i in range(len(pts)):
        res = G.project_tile(pts.loc[i], pts.rot[i], pts.bounds_min[i], pts.bounds_max[i], surface)
        if res is not None:
            pts.loc[i], pts.rot[i] = res
    return pts


def tile_points(area):
    """`Subgraph_34 Fill_Areas_Uniformly` (150) then `Subgraph_48` (+15 cm) on one plaza lot."""
    locs, yaw = G.fill_uniform(area.outer, area.z, TILE_EXTENT_CM)
    pts = Points()
    e = TILE_EXTENT_CM
    for p in locs:
        pts.add((p[0], p[1], p[2] + TILE_LIFT_CM), rot=(0.0, yaw, 0.0), bounds_min=(-e, -e, -e),
                bounds_max=(e, e, e), steepness=1.0)
    return pts


def tiles(kept, surface, draws, loader):
    """The tile chain on the kept plaza lots: `[(letter, Points)]` in Gather_1's order, and the sets."""
    sets = [project(tile_points(p), surface) for p in kept]
    way = draws.ways(len(sets))
    if loader is None or not any(len(s) for s in sets):
        return [], sets
    table = loader([path for _k, path in TILE_CALLS])
    by = G.assign_ways(sets, way, table, TILE_CALLS, TILE_OFFSET)
    return [(k, by[k]) for k, _p in TILE_CALLS if k in by], sets


def tree_areas(src, trees, ops):
    """`Subgraph_24`: the tree-side lots, the unbuildable lots and the cleaned undividable districts (its
    input order), each less the union of the highway; then `Subgraph_1`'s second input, the small park."""
    return A.exclusion(trees + src["unbuildable"] + undividable(src, ops), src["highway"], ops) + small_park(src, ops)


def tree_points(areas, surface, rng):
    """`Subgraph_1 Fill_Areas_Randomly` (0.02 / m2) then `Subgraph_19` onto the terrain: one point set per
    area that holds a point (an empty sample is no item, as officially)."""
    e = TREE_EXTENT_CM
    out = []
    for a in areas:
        locs = G.fill_random(a, TREES_PER_M2, rng)
        if not locs:
            continue
        pts = Points()
        for p in locs:
            pts.add(p, bounds_min=(-e, -e, -e), bounds_max=(e, e, e), steepness=1.0,
                    seed=AS._i32(rng.getrandbits(32)))
        pts = project(pts, surface)
        if len(pts):
            out.append(pts)
    return out


def leftover(inputs, params, ops, draws, loader=None):
    """The whole computation; returns ({pin: [value]}, notes)."""
    out = {pin: [] for pin in OUTPUTS}
    src = read(inputs)
    surface = _surface(inputs)
    kept, published, trees = split(src, params, draws)
    out["PlazaLots"] = published
    out["ReservedPlazaAreas"] = setback(kept, ops)
    out["UnderHighwayAreas"] = setback(src["under"], ops)
    out["SmallCourtyardAreas"] = setback(src["small_yards"], ops)
    out["MediumCourtyardAreas"] = setback(src["medium_yards"], ops)
    out["SkirtAreas"] = [lift(p, PLAZA_LIFT_CM) for p in src["skirt"]]
    placed, sets = tiles(kept, surface, draws, loader)
    out["GroundTiles"] = placed
    areas = tree_areas(src, trees, ops)
    out["TreePoints"] = tree_points(areas, surface, draws.rng)
    notes = ["split: %d reserved -> %d plaza (%d kept, %d published), %d trees"
             % (len(src["reserved"]), len(kept) + len(published), len(kept), len(published), len(trees)),
             "tiles: %d lots, %d tiles" % (len(sets), sum(len(s) for s in sets)),
             "trees: %d areas, %d points in %d sets" % (len(areas), sum(len(s) for s in out["TreePoints"]),
                                                         len(out["TreePoints"]))]
    return out, notes


def tagged(raw):
    out = {pin: [] for pin in OUTPUTS}
    out["PlazaLots"] = [(p, ["reservedLots"]) for p in raw["PlazaLots"]]
    for pin in ("ReservedPlazaAreas", "UnderHighwayAreas", "SmallCourtyardAreas", "MediumCourtyardAreas",
                "SkirtAreas"):
        out[pin] = [(p, [pin]) for p in raw[pin]]
    out["GroundTiles"] = [(pts, ["GroundTiles", "SM_Plaza_Square_" + k]) for k, pts in raw["GroundTiles"]]
    out["TreePoints"] = [(pts, ["TreePoints"]) for pts in raw["TreePoints"]]
    return out


def run(inputs, params, ctx):
    loader = getattr(ctx.ops, "assets", None)
    raw, notes = leftover(inputs, params, ctx.ops, Draws(ctx.rng), loader)
    ctx.notes += notes
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): no tiles assigned")
    return tagged(raw)
