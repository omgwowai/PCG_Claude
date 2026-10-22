"""PyWorld W7 -- vegetation and rocks (视频步骤 7：放弃生态模拟，改用区域遮罩 + 散布规则；沿路清空；密度可控).

Data layers from the final terrain: slope, height above the valley floor (a 586 m sliding minimum) and D8 flow
accumulation (gullies). A jittered 7 m grid over the land picks a biome per sample from the rule table (rock,
riparian by the river and in gullies, alpine high up, forest on slopes, meadow with clumps of birch), keeps it with
the biome's density (x Density), clears roads, streets, the river, bridges, footprints, plazas and fields, and
places the species at the exact terrain height (the surface's own ray) sunk a little. Grass tufts on a 4.5 m grid
in meadows and by the river."""
import math

from pypcg.stage_api import Param
from pypcg.stages.w03_river import terrain_sets
from pypcg.world import hydro, noise, points as WP, rules, scatter

STAGE = 107
RECORD = "w07"
DOC = """PyWorld W7 Vegetation (植被与岩石): biome rules on slope, height above the valley, flow and the river;
jittered scattering with clearings for roads, river, bridges and settlements; trees, rocks and grass."""
RANDOM = True
PARAMS = {"Density": Param(1.0, "Multiplies every biome's density", type="Double"),
          "GrassDensity": Param(1.0, "Multiplies the grass density", type="Double"),
          "Extent": Param(135000.0, "Half size of the square that is scattered (cm)", type="Double")}
INPUTS = {"Terrain": "points", "Surface": "surface", "Upstream": "any"}
OUTPUTS = ("Trees", "Rocks", "Grass", "Summary")
BASE_CELL = 700.0
GRASS_CELL = 450.0
GRASS_HALF = 100000.0
FLOOR_CELLS = 100
CLUMP_CM = 15000.0


def _summary(**kw):
    base = {"trees": 0, "rocks": 0, "grass": 0, "alder_share_riparian": 0.0, "alder_share_all": 0.0, "excluded": 0}
    base.update({"biome_" + b: 0 for b in rules.BIOMES})
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    if not sets:
        return {"Trees": [], "Rocks": [], "Grass": [], "Summary": _summary()}
    surface = next((v for v, _t in inputs.get("Surface", []) if hasattr(v, "height")), None)
    slope = [lat.slope_deg(k) if z is not None else None for k, z in enumerate(lat.z)]
    floor = hydro.min_filter(lat, FLOOR_CELLS)
    acc = hydro.flow_accumulation(lat)
    ex = scatter.upstream_exclusions(inputs.get("Upstream", []))
    rng, seed = ctx.rng, ctx.seed
    half = (lat.n - 1) * lat.s / 2.0
    cx, cy = lat.x0 + half, lat.y0 + half
    e = min(params["Extent"], half)
    trees, rocks, grass, counts = [], [], [], {b: 0 for b in rules.BIOMES}
    alder = {"riparian": 0, "all": 0}
    excluded = 0

    def sample(x, y):
        k = lat.nearest(x, y)
        if k is None:
            return None
        return {"z": lat.z[k], "slope": slope[k], "rel": lat.z[k] - floor[k], "acc": acc[k], "river": ex.river_gap(x, y)}

    def height(x, y):
        h = surface.height(x, y) if surface is not None else None
        return h if h is not None else lat.height(x, y)
    for x, y in scatter.jittered(cx - e, cy - e, cx + e, cy + e, BASE_CELL, rng):
        s = sample(x, y)
        b = rules.biome_of(s) if s else None
        if b is None:
            continue
        spec = rules.BIOMES[b]
        clump = noise.value(x / CLUMP_CM, y / CLUMP_CM, seed + 3)
        p = spec["density"] * ((1.0 - spec["clump"]) + spec["clump"] * 2.0 * clump) * params["Density"]
        if rng.random() >= p:
            continue
        tree = spec["kind"] == "Tree"
        if not ex.clear(x, y, 300.0 if tree else 150.0, 150.0 if tree else 0.0, 300.0 if tree else 150.0):
            excluded += 1
            continue
        mesh, sc = rules.pick_species(spec, rng)
        h = height(x, y)
        if h is None:
            continue
        yaw = rng.uniform(0.0, 360.0)
        if tree:
            trees.append(((x, y, h - spec["sink"]), (0.0, yaw, 0.0), (sc, sc, sc), mesh))
            alder["all"] += mesh in rules.ALDERS
            if b == "riparian":
                alder["riparian"] += mesh in rules.ALDERS
        else:
            rocks.append(((x, y, h - spec["sink"]), (rng.uniform(-8.0, 8.0), yaw, rng.uniform(-8.0, 8.0)), (sc, sc, sc), mesh))
        counts[b] += 1
    g = rules.GRASS
    ge = min(GRASS_HALF, half)
    for x, y in scatter.jittered(cx - ge, cy - ge, cx + ge, cy + ge, GRASS_CELL, rng):
        s = sample(x, y)
        if not s or rules.biome_of(s) not in ("meadow", "riparian") or s["slope"] >= 15.0:
            continue
        c2 = noise.value(x / 4000.0, y / 4000.0, seed + 7)
        if rng.random() >= g["density"] * params["GrassDensity"] * (0.4 + 0.6 * c2):
            continue
        if not ex.clear(x, y, 50.0, 0.0, 100.0):
            continue
        h = height(x, y)
        if h is None:
            continue
        sc = rng.uniform(*g["scale"])
        grass.append(((x, y, h - g["sink"]), (0.0, rng.uniform(0.0, 360.0), 0.0), (sc, sc, sc), rng.choice(g["meshes"])))
    n_rip = counts["riparian"]
    summary = dict(trees=len(trees), rocks=len(rocks), grass=len(grass), excluded=excluded,
                   alder_share_riparian=alder["riparian"] / n_rip if n_rip else 0.0,
                   alder_share_all=alder["all"] / len(trees) if trees else 0.0,
                   **{"biome_" + b: n for b, n in counts.items()})
    ctx.notes.append("%d trees, %d rocks, %d grass" % (len(trees), len(rocks), len(grass)))
    return {"Trees": [(WP.mesh_points(trees), ["Tree"])] if trees else [],
            "Rocks": [(WP.mesh_points(rocks), ["Rock"])] if rocks else [],
            "Grass": [(WP.mesh_points(grass), ["Grass"])] if grass else [], "Summary": _summary(**summary)}
