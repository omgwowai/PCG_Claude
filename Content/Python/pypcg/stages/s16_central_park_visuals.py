"""Stage 16 -- CentralParkVisuals (PCG_4_2_CentralPark_Visuals, 中央公园视觉): the VEGETATION node.

The stage's main Python node (its record is `s16`, the one V2 copies per seed): everything the official graph
computes after `Spawn_Border_Road` and `Spawn_Met_Building` -- the road footprints grown 8 m, the forest
areas (the vegetation areas less the forest exclusion, the lakes, the roads and the Met), their 50/50 split
for the two densities, the two tree scatters (fill, jitter, density noise, terrain fit, kit assignment,
upright), and the Met rooftop dropped 10 cm for its rooftop assemblies. The geometry upstream is
`s16_park_geometry`; the three grass chains run native on this node's split (Step F, s16.md 3.2).
`docs/pypcg/stages/s16.md` section 2.2 names the official node behind every step.
"""
import math

from pypcg import geo
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stage_api import Param

STAGE = 16
DOC = """CentralParkVisuals (中央公园视觉): the central park's dressing -- four transverse lines and the
border road, sidewalks, corners and the walkpaths drawn across it, the two lakes (water plane, city-edge
sidewalk, a bed 50 cm below the lowest shore written into the terrain), the Met (a CHA building with its
rooftop), and the forest: the park less the paths, the roads, the lakes, the Met and the forest-exclusion
zone, split 50/50 into a sparse and a dense half, each with its own trees and wild grass. Sizes in cm."""
RANDOM = True
PARAMS = {
    "UseMegaplantsTrees": Param(False, "Use the Megaplants trees for the forest instead of the Black Alder "
                                       "field trees", type="Bool"),
}
# ParkAreas / Exclusions: s16_park_geometry's; RoadFootprints: Spawn_Border_Road.Footprints; MetRoofs:
# Spawn_Met_Building's "Rooftops Footprints"; MeshTerrain: Subgraph_1 (Final).
INPUTS = {"ParkAreas": "polygon", "Exclusions": "polygon", "RoadFootprints": "polygon", "MetRoofs": "spline",
          "MeshTerrain": "surface"}
OUTPUTS = ("Selected", "Unselected", "Trees", "MetRoofsLowered")

ROAD_EXPAND_CM = 800.0                   # Expand_Border_Footprint Expand (its title says 425)
SPLIT_RATIO = 0.5                        # Filter_5_Areas Ratio
DENSITY_THRESHOLD = 0.4000000059604645   # Filter_By_Density(_2) FilterValue (Float 0.4), Operator Greater
MET_ROOF_DROP = -10.0                    # Subgraph_54 offset Z
# Fill_Forest (Unselected) / Fill_Forest_2 (Selected): Fill_Areas_Randomly overrides
FILLS = {"Unselected": {"ppsm": 0.05, "sampling_extent": 50.0},
         "Selected": {"ppsm": 0.02, "sampling_extent": 50.0}}
FILL_EXTENT = 50.0                       # OutputPointsExtents
FILL_POSITION_RANGE = (200.0, 200.0, 0.0)
FILL_ROTATION_RANGE = (5.0, 180.0, 5.0)  # (pitch, yaw, roll)
FILL_SCALE_RANGE = 0.25

FIELD_TREES = tuple("/CitySamplePCG/BlackAlder/Geometry/PivotPainter/SM_BlackAlder_Field_%02d_PP."
                    "SM_BlackAlder_Field_%02d_PP" % (k, k) for k in (5, 4, 3, 2))
_MEGA = "/CitySamplePCG/Megaplants/"
MEGA_TREES = {
    "Unselected": (_MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_A.SM_Black_Alder_01_A",
                   _MEGA + "Tree_Common_Hazel/Tree_Common_Hazel_01/SM_Common_Hazel_01_A.SM_Common_Hazel_01_A",
                   _MEGA + "Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SM_Norway_Maple_Forest_01_A."
                           "SM_Norway_Maple_Forest_01_A",
                   _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_B.SM_Black_Alder_01_B",
                   _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_C.SM_Black_Alder_01_C",
                   _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_D.SM_Black_Alder_01_D",
                   _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_B.SM_European_Aspen_01_B",
                   _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_C.SM_European_Aspen_01_C",
                   _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_D.SM_European_Aspen_01_D"),
    "Selected": (_MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_A.SM_Black_Alder_01_A",
                 _MEGA + "Tree_Common_Hazel/Tree_Common_Hazel_01/SM_Common_Hazel_01_A.SM_Common_Hazel_01_A",
                 _MEGA + "Tree_European_Beech/Tree_European_Beech_01/SM_European_Beech_01_A.SM_European_Beech_01_A",
                 _MEGA + "Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SM_Norway_Maple_Forest_01_A."
                         "SM_Norway_Maple_Forest_01_A",
                 _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_B.SM_Black_Alder_01_B",
                 _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_C.SM_Black_Alder_01_C",
                 _MEGA + "Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_D.SM_Black_Alder_01_D",
                 _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_B.SM_European_Aspen_01_B",
                 _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_C.SM_European_Aspen_01_C",
                 _MEGA + "Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_D.SM_European_Aspen_01_D"),
}
# The four Assign_Assets calls (official overrides, keys as `geo.assets` reads them)
FIELD_SETTINGS = {"Unselected": {"scale_offset": {"X": 0.7, "Y": 1, "Z": 1},                       # Subgraph_33
                                 "random_scale_range": {"X": 0.2, "Y": 0, "Z": 0},
                                 "random_rotation_range": {"X": 0, "Y": 0, "Z": 180},
                                 "use_index_attribute": False},
                  "Selected": {"scale_offset": {"X": 0.7, "Y": 1, "Z": 1},                         # Subgraph_38
                               "random_scale_range": {"X": 0.15, "Y": 0, "Z": 0},
                               "random_rotation_range": {"X": 0, "Y": 0, "Z": 180}}}
MEGA_SETTINGS = {"Unselected": {"random_scale_range": {"X": 0.15, "Y": 0.15, "Z": 0.15},           # Assign_Trees
                                "random_rotation_range": {"X": 0, "Y": 0, "Z": 180}},
                 "Selected": {"random_scale_range": {"X": 0.15, "Y": 0.15, "Z": 0.15},             # Assign_Trees_2
                              "random_rotation_range": {"X": 2, "Y": 2, "Z": 180}}}
SIDES = ("Unselected", "Selected")       # Fill_Forest (Unselected) is drawn first


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def _polygons(inputs, pin):
    out = []
    for v, _tags in inputs.get(pin, []):
        if isinstance(v, Polygon) and len(v.outer) >= 3:
            out.append(v)
        elif isinstance(v, Spline) and v.closed and len(v.points) >= 3:
            out.append(A.area_of(v))
    return out


# ---- 12-14. the forest areas and the split -----------------------------------------------------------
def road_footprints(polys, ops):
    """`Expand_Border_Footprint` (`Transform_Areas_Expand`, 800, no union): one grown polygon per footprint."""
    out = []
    for p in polys:
        out += A.in_frame(p, lambda q: A.expand([q], ROAD_EXPAND_CM, ops))
    return out


def forest_areas(areas, exclusions, roads, ops):
    """`Exclude_Roads_From_Areas`: each vegetation area less the union of the forest exclusion, the lakes,
    the grown road footprints and the grown Met (`Subgraph_35`'s `@Data.Test` is not written: nothing reads
    it)."""
    clips = list(exclusions) + list(roads)
    return [Polygon(p.outer, p.holes, 0.0) for p in A.exclusion(areas, clips, ops)]


def split(areas, rng):
    """`Filter_5_Areas` (`Filter_RandomChoice`, Ratio 0.5, `RandomPerDataset`): one Bernoulli per area."""
    keep = geo.keep_each(len(areas), SPLIT_RATIO, rng)
    sel = [a for a, k in zip(areas, keep) if k]
    uns = [a for a, k in zip(areas, keep) if not k]
    return sel, uns


# ---- 15. the trees -------------------------------------------------------------------------------------
def scatter(poly, side, rng):
    """`Fill_Forest(_2)` on ONE area: the sampler's grid (`geo.ground.fill_random`), then the primitive's
    `TransformPoints_1` -- a rotation drawn in +-`RotationRange` (pitch, yaw, roll), the position moved by an
    offset drawn in +-`PositionRange` turned by that rotation, one uniform scale in 1 +- `ScaleRange` -- and
    `OutputPointsExtents` 50 as the box. Python's own numbers (E2)."""
    f = FILLS[side]
    pts = Points()
    for loc in G.fill_random(poly, f["ppsm"], rng, f["sampling_extent"]):
        rot = tuple(rng.uniform(-r, r) for r in FILL_ROTATION_RANGE)
        q = AS.quat_of(*rot)
        off = tuple(rng.uniform(-r, r) for r in FILL_POSITION_RANGE)
        d = geo.quat_rotate(q, off)
        s = rng.uniform(1.0 - FILL_SCALE_RANGE, 1.0 + FILL_SCALE_RANGE)
        e = FILL_EXTENT
        pts.add((loc[0] + d[0], loc[1] + d[1], loc[2] + d[2]), rot=rot, scale=(s, s, s),
                bounds_min=(-e, -e, -e), bounds_max=(e, e, e), steepness=1.0)
    return pts


def dense_enough(pts, rng):
    """`Noise_Forest_Density(_2)` (`$Density` uniform in [0, 1]) then `Filter_By_Density(_2)` (> 0.4, a float):
    the points kept, their density the drawn noise."""
    keep = []
    for i in range(len(pts)):
        dens = rng.random()
        if dens > DENSITY_THRESHOLD:
            pts.density[i] = dens
            keep.append(i)
    return pts.take(keep)


def project(pts, surface):
    """`Subgraph_10` / `Subgraph_7` `Custom_Projector_with_rotation_fix` on every point (its scale and
    rotation place the three corner probes); a miss keeps the point at density 0, its z doubled (stage 13's
    measured miss rule)."""
    if surface is None:
        return pts
    for i in range(len(pts)):
        loc, rot, hit = G.project_point(pts.loc[i], pts.rot[i], pts.bounds_min[i], pts.bounds_max[i], surface,
                                        scale=pts.scale[i])
        pts.loc[i], pts.rot[i] = loc, rot
        if not hit:
            pts.density[i] = 0.0
    pts.quat = None
    return pts


def upright(pts):
    """`AttributeMathsOp_3/4`: roll and pitch 0."""
    for i in range(len(pts)):
        r = pts.rot[i]
        pts.rot[i] = (0.0, r[1], 0.0)
    pts.quat = None
    return pts


def trees(sets, mega, surface, rng, loader):
    """Per side, every area's scatter (one point set per area, as the primitive keeps them), the density
    filter and the terrain fit; then `Branch_6` / `Branch_7` -> the side's `Assign_Assets` (every area of the
    side merged, `$Seed += dataIndex`) and upright. Returns `[(side, Points)]` in `AttributeMathsOp_3`'s
    input order (Megaplants: Selected first; field trees: Unselected first -- the official u17 is [1 754
    unselected, 444 selected])."""
    out, counts = [], {}
    for side in SIDES:
        per_area = []
        filled = kept = 0
        for poly in sets.get(side, []):
            pts = scatter(poly, side, rng)
            filled += len(pts)
            pts = dense_enough(pts, rng)
            kept += len(pts)
            per_area.append(project(pts, surface))
        counts[side] = (filled, kept)
        targets = Points()
        for idx, s in enumerate(per_area):
            for j in range(len(s)):
                targets.add(s.loc[j], rot=s.rot[j], scale=s.scale[j], density=s.density[j],
                            bounds_min=s.bounds_min[j], bounds_max=s.bounds_max[j], color=s.color[j],
                            steepness=s.steepness[j], seed=AS._i32(int(s.seed[j]) + idx))
        if not len(targets) or loader is None:
            continue
        paths = MEGA_TREES[side] if mega else FIELD_TREES
        settings = (MEGA_SETTINGS if mega else FIELD_SETTINGS)[side]
        picks = AS.choose(len(targets), paths, rng)
        items = AS.expand_items(targets, loader(list(paths)), picks, dict(settings, rng=rng))
        for item in items:
            if len(item):
                out.append((side, upright(item)))
    # AttributeMathsOp_3's InA: Assign_Trees_2 (Selected), Assign_Trees (Unselected), Subgraph_33
    # (Unselected), Subgraph_38 (Selected) -- only one branch of each side carries points.
    order = {"Selected": 0, "Unselected": 1} if mega else {"Unselected": 0, "Selected": 1}
    out.sort(key=lambda t: order[t[0]])
    return out, counts


# ---- 16. the Met rooftop drop ---------------------------------------------------------------------------
def lowered(roofs):
    """`Subgraph_54 Transform_Offset` (-10, per point) on the Met rooftop spline: a linear closed spline's
    control points move straight down (its control points are level, so the rotation is yaw-only)."""
    out = []
    for v in roofs:
        pts = [(p[0], p[1], p[2] + MET_ROOF_DROP) for p in v.points]
        out.append(Spline(pts, closed=v.closed, linear=v.linear,
                          tangents=[(tuple(a), tuple(b)) for a, b in v.tangents] if v.tangents else None))
    return out


def vegetation(inputs, params, ops, rng, loader):
    """`({pin: [(value, tags)]}, notes)`."""
    out = {pin: [] for pin in OUTPUTS}
    surface = _surface(inputs)
    roofs = [v for v, _t in inputs.get("MetRoofs", []) if isinstance(v, Spline) and len(v.points) >= 3]
    out["MetRoofsLowered"] = [(s, ["MetRoofsLowered"]) for s in lowered(roofs)]
    areas = _polygons(inputs, "ParkAreas")
    if not areas or ops is None:
        return out, ["no park areas: no forest"]
    roads = road_footprints(_polygons(inputs, "RoadFootprints"), ops)
    forest = forest_areas(areas, _polygons(inputs, "Exclusions"), roads, ops)
    sel, uns = split(forest, rng)
    out["Selected"] = [(p, ["Selected"]) for p in sel]
    out["Unselected"] = [(p, ["Unselected"]) for p in uns]
    made, counts = trees({"Selected": sel, "Unselected": uns}, bool(params["UseMegaplantsTrees"]), surface, rng,
                         loader)
    out["Trees"] = [(pts, ["Trees", side]) for side, pts in made]
    notes = ["areas %d, road footprints %d -> forest %d (selected %d, unselected %d)"
             % (len(areas), len(roads), len(forest), len(sel), len(uns)),
             "trees: %s; items %d, points %d; UseMegaplantsTrees=%s"
             % (counts, len(made), sum(len(p) for _s, p in made), bool(params["UseMegaplantsTrees"]))]
    if loader is None:
        notes.append("no asset loader (ctx.ops.assets): no trees assigned")
    return out, notes


def run(inputs, params, ctx):
    out, notes = vegetation(inputs, params, ctx.ops, ctx.rng, getattr(ctx.ops, "assets", None))
    ctx.notes += notes
    return out
