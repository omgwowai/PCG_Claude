"""Stage 18, second Python node -- the outer forest after the two texture writes (OuterForest, 外围林地).

`s18_outer_forest` scatters the forest points; the two official `Write_Attribute_fromTexture` nodes stay
NATIVE between the two Python nodes (`Subgraph_12` writes `$scale` from the texture's G channel remapped to
ScaleMin..ScaleMax, `Subgraph_2` writes `index` remapped to 1..9; pure Python cannot read the texture's pixels,
spec 4.3). This node does everything after them, as the official graph does (docs/pypcg/stages/s18.md 2):

  AttributeNoise_2              `index` += U(-0.5, 0.5)          [CreateConstant_2 0.5, AttributeMathsOp_5 x -1]
  FilterDataByType_5, MergePoints_0, AttributeReduce_0 / 1
                                the min and max of `index` over every point set together
  AttributeRemap_1              `index` from [min, max] to [0, 10] [AttributeMathsOp_6: CreateConstant_3 9 + 1]
  Subgraph_10 Transform_Project positions onto the final mesh terrain (`MeshTerrain`)
  FilterDataByType_1, AttributeFilter_0
                                above water: `$Position.Z > 0` (the node's default threshold), below: the rest
  Subgraph_11 Write_DistanceFrom every projected point's 2D distance to the nearest point above water, capped
                                at 50 m, / 50 m, remapped from its min..max to 1..0 (`geo.distance`)
  CopyAttributes_0, AttributeNoise_0
                                -> `$Density` (a float), + U(-0.3, 0.3), clamped to 0..1 (density always is)
  FilterDataByType_2, AttributeFilter_2
                                the points whose density is greater than 0.8 (near the shore or on land)
  Subgraph_14 Write_DistanceFrom their distance to the nearest point BELOW water, capped at 100 m, / 100 m,
                                remapped to 0..1 (the deep-forest weight: 1 far inland)
  CopyAttributes_1, AttributeNoise_1, AttributeRemap_0
                                -> `$Density`, + U(-0.1, 0.1), clamped; then 0..1 -> 0.6..1
  AttributeMathsOp_3            `$Scale *= $Density`
  FilterDataByType_3, AttributeFilter_3
                                `$Position.Z > -450` (cut the points well below water)
  Branch_0                      `UseMegaPlantsTrees` false -> `Subgraph_15` (Black Alder field trees, ScaleOffset
                                0.7), true -> `Subgraph_18` (Megaplants): `Assign_Assets` with `UseIndexattribute`
                                on `Index` (`geo.assets.index_picks`: truncated, an index naming no entry takes entry
                                0), random rotation (+-2, +-2, +-180) and scale (1 +- 0.2); the same two calls as
                                stage 13's (`s13_leftover_trees.FOREST` / `MEGA`), reused, not copied
  Branch_1                      `Partitioned` false: everything to the kept `SpawnForest_0`

Every noise draw is Python's own (`ctx.rng`, spec E2); every other step was measured against the official
graph run with a substitute texture (s18.md 6): bit for bit.

ON THE DEMO LEVEL THIS NODE RECEIVES NOTHING: the official texture `/Game/Textures/Noise/T_CloudNoise_4k` is not
in this project (trap 66), so both texture writes output no points, officially and in the port.
"""
from pypcg.geo import Points
from pypcg.geo import assets as AS
from pypcg.geo import distance as D
from pypcg.geo.frames import f32
from pypcg.stage_api import Param
from pypcg.stages import s13_leftover_trees as T13

STAGE = 18
RECORD = "s18_trees"
DOC = """OuterForest, trees: the forest points after the native texture writes, their species index jittered
and normalised, projected onto the final terrain, kept near the shore and on land, scaled down towards the
water, and assigned the tree mesh their index names (Black Alder field trees, or Megaplants with
UseMegaPlantsTrees)."""
RANDOM = True
PARAMS = {"UseMegaPlantsTrees": Param(False, "Use the Megaplants trees instead of the Black Alder field trees",
                                      type="Bool")}
INPUTS = {"ForestPoints": "points", "MeshTerrain": "surface"}
OUTPUTS = ("Trees",)

INDEX_ATTR = "index"                   # what Subgraph_2 writes (Attribute override)
INDEX_JITTER = f32(0.5)                # CreateConstant_2 (Float 0.5); AttributeMathsOp_5 gives the -0.5
INDEX_OUT_MAX = 9.0 + 1.0              # AttributeMathsOp_6: CreateConstant_3 (Float 9) + 1 (Add)
WATER_LEVEL_CM = 0.0                   # AttributeFilter_0: constant threshold left at its default Double 0
SHORE_MAX_CM = 5000.0                  # Subgraph_11 MaximumDistance
SHORE_REMAP = (1.0, 0.0)               # Subgraph_11 RemapOutputMin / Max
SHORE_NOISE = f32(0.3)                 # CreateConstant_0 (Float 0.3); AttributeMathsOp_2 x -1
SHORE_KEEP = 0.8                       # AttributeFilter_2 (Double 0.8, Greater)
DEEP_MAX_CM = 10000.0                  # Subgraph_14 MaximumDistance
DEEP_REMAP = (0.0, 1.0)                # Subgraph_14 RemapOutputMin / Max
DEEP_NOISE = f32(0.1)                  # CreateConstant_1 (Float 0.1); AttributeMathsOp_4 x -1
SCALE_FLOOR = 0.6                      # AttributeRemap_0 OutRangeMin (In 0..1, Out max 1: the defaults)
CUT_Z_CM = -450.0                      # AttributeFilter_3 (Greater)


def sets_of(inputs):
    """The point sets on `ForestPoints` (one per forest area), as COPIES the steps may change in place."""
    out = []
    for v, _tags in inputs.get("ForestPoints", []):
        if isinstance(v, Points) and len(v):
            out.append(v.take(range(len(v))))
    return out


def surface_of(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def _uniform(lo, hi, rng):
    """`FRandomStream::FRandRange(lo, hi)`: lo + (hi - lo) x a draw, with Python's draw."""
    return lo + (hi - lo) * rng.random()


def jitter_index(sets, rng):
    """`AttributeNoise_2` (Add, no clamp: `index` is not the density): one draw per point, set by set."""
    for s in sets:
        col = s.attrs.get(INDEX_ATTR)
        if col is None:
            continue
        for j in range(len(col)):
            col[j] = col[j] + _uniform(-INDEX_JITTER, INDEX_JITTER, rng)


def normalise_index(sets):
    """`AttributeReduce_0/1` over the merged sets, then `AttributeRemap_1` (bAllowInverseRange) from [min, max]
    to [0, 10] on every set. Measured: all 308 785 official values bit for bit."""
    values = [v for s in sets for v in s.attrs.get(INDEX_ATTR, [])]
    if not values:
        return None
    lo, hi = min(values), max(values)
    for s in sets:
        if INDEX_ATTR in s.attrs:
            s.attrs[INDEX_ATTR] = D.remap(s.attrs[INDEX_ATTR], lo, hi, 0.0, INDEX_OUT_MAX)
    return lo, hi


def project(sets, surface):
    """`Subgraph_10 Transform_Project` (ProjectPositions only): each point's z becomes the surface's height
    under it; a point the surface misses keeps its z (stage 8's reading of the node). Nothing else changes
    (measured: scale, density, seed, rotation, box, colour and x, y identical before and after). With no
    surface the primitive passes the points through (`Branch_4`, "Branch If projecting onto a surface"); in
    this graph that cannot happen with points present, since the scatter needs the same terrain."""
    if surface is None:
        return sets
    for s in sets:
        for j in range(len(s)):
            p = s.loc[j]
            h = surface.height(p[0], p[1])
            if h is not None:
                s.loc[j] = (p[0], p[1], float(h))
    return sets


def split_water(sets):
    """`AttributeFilter_0`: per set, (indices above water, indices at or below)."""
    return [([j for j in range(len(s)) if s.loc[j][2] > WATER_LEVEL_CM],
             [j for j in range(len(s)) if not s.loc[j][2] > WATER_LEVEL_CM]) for s in sets]


def centres(sets, picks):
    """The merged targets' octree centres (`geo.distance.target_centre`), z dropped (ComputeIn2D)."""
    out = []
    for s, idx in zip(sets, picks):
        for j in idx:
            r = s.rot[j]
            q = AS.quat_of(*r) if any(r) else None
            out.append(D.target_centre(s.loc[j], s.scale[j], s.bounds_min[j], s.bounds_max[j], q))
    return out


def densities(values, noise, rng):
    """`CopyAttributes` (the double into the float `$Density`) then `AttributeNoise` (Add, the density
    clamped to 0..1: `bClampResult` is forced for `$Density`)."""
    out = []
    for v in values:
        d = f32(f32(v) + _uniform(-noise, noise, rng))
        out.append(min(max(d, 0.0), 1.0))
    return out


def trees(sets, surface, rng, info=None):
    """Everything from the index jitter to the z cut: one point set per input set (empty ones kept, as the
    nodes keep empty data), each point carrying its final density and scale. `info` (a dict), when given,
    receives each step's count and the index range, which the run notes."""
    info = {} if info is None else info
    jitter_index(sets, rng)
    info["index_range"] = normalise_index(sets)
    project(sets, surface)
    water = split_water(sets)
    info["above"] = sum(len(a) for a, _b in water)
    info["below"] = sum(len(b) for _a, b in water)
    above = centres(sets, [a for a, _b in water])
    below = centres(sets, [b for _a, b in water])
    shore = D.distance_from([[(p[0], p[1]) for p in s.loc] for s in sets], above, SHORE_MAX_CM, *SHORE_REMAP)
    kept = []
    for s, values in zip(sets, shore):
        s.density = densities(values, SHORE_NOISE, rng)
        s.attrs["distance"] = list(values)
        s.types["distance"] = "Double"
        kept.append(s.take([j for j in range(len(s)) if s.density[j] > SHORE_KEEP]))
    info["near_shore"] = sum(len(s) for s in kept)
    deep = D.distance_from([[(p[0], p[1]) for p in s.loc] for s in kept], below, DEEP_MAX_CM, *DEEP_REMAP)
    slope = (1.0 - SCALE_FLOOR) / (1.0 - 0.0)
    out = []
    for s, values in zip(kept, deep):
        s.attrs["distance"] = list(values)
        dens = [f32(slope * (d - 0.0) + SCALE_FLOOR) for d in densities(values, DEEP_NOISE, rng)]
        s.density = dens
        s.scale = [tuple(c * dens[j] for c in s.scale[j]) for j in range(len(s))]
        out.append(s.take([j for j in range(len(s)) if s.loc[j][2] > CUT_Z_CM]))
    info["cut"] = sum(len(s) for s in out)
    return out


def assign(sets, mega, loader, rng):
    """`Branch_0` then `Subgraph_15` / `Subgraph_18` (`Assign_Assets`): the merged targets (`$Seed +=
    dataIndex`), each taking the entry its `index` names; static meshes, so the output is the moved targets
    alone (`geo.assets.expand_items`)."""
    targets = AS.merge_targets([(s, ()) for s in sets])
    if not len(targets):
        return []
    paths, settings = (T13.MEGA, T13.MEGA_SETTINGS) if mega else (T13.FOREST, T13.FOREST_SETTINGS)
    table = loader(list(paths))
    return AS.expand_items(targets, table, None, dict(settings, rng=rng))


def run(inputs, params, ctx):
    import time
    out = {"Trees": []}
    sets = sets_of(inputs)
    if not sets:
        ctx.notes.append("trees: no points after the texture writes")
        return out
    surface = surface_of(inputs)
    t0 = time.perf_counter()
    info = {}
    placed = trees(sets, surface, ctx.rng, info)
    n_in = sum(len(s) for s in sets)
    ctx.notes.append("trees: %d points in %d sets; index range %r; above water %d, below %d; near the shore %d; "
                     "above the cut %d (%.2f s)" % (n_in, len(sets), info.get("index_range"), info.get("above", 0),
                                                   info.get("below", 0), info.get("near_shore", 0),
                                                   info.get("cut", 0), time.perf_counter() - t0))
    loader = getattr(ctx.ops, "assets", None)
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): no trees assigned")
        return out
    mega = bool(params.get("UseMegaPlantsTrees", False))
    items = assign(placed, mega, loader, ctx.rng)
    out["Trees"] = [(pts, ["Trees"]) for pts in items]
    ctx.notes.append("trees: %d assigned (%s)" % (len(items[-1]) if items else 0,
                                                  "Megaplants" if mega else "Black Alder field"))
    return out
