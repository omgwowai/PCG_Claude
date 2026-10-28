"""PyWorld W7 -- vegetation communities and rocks (视频步骤 7：区域遮罩 + 散布规则；沿路清空；密度可控。
2026-10-23 起做成分层的生态群落：docs/superpowers/specs/2026-10-23-pyworld-vegetation-ecology-design.md).

Fields on the final terrain's vertex lattice (slope, height above the valley floor, flow, distances to the river,
roads and buildings, sun exposure, moisture, forest potential with ragged noise edges) give every sample a community:
forest, forest edge, meadow, river bank, montane, rock or village. Layers, in order: rock clusters, canopy trees with
spacing by crown (species mix per community, young trees and pioneers on edges, groves in meadows), shrubs (edges,
banks, forest gaps), hedgerows around the fields and along the roads through open land, roots / leaf litter / ivy
under mature trees, dead wood (logs across the slope, stumps, branches, twigs), pebbles along the banks, and ground
plants in clumps (grass, flowers each in patches of their own, ferns, litter, moss). Heights come from the terrain's
own triangles; small plants, logs and rocks follow the slope."""
from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import WORLD_HALF_CM, ecology, grow, points as WP, scatter
from pypcg.world.flora import ALDERS, SPECIES

STAGE = 107
RECORD = "w07"
DOC = """PyWorld W7 Vegetation (植被群落): ecological fields -> communities (forest, edge, meadow, river bank, montane,
rock, village) -> layered scattering of rocks, trees, shrubs, hedgerows, dead wood and ground plants, with clearings
for roads, river, bridges and settlements."""
RANDOM = True
PARAMS = {"Density": Param(1.0, "Multiplies the tree density", type="Double"),
          "ShrubDensity": Param(1.0, "Multiplies the shrub density", type="Double"),
          "GroundDensity": Param(1.0, "Multiplies the ground plant density", type="Double"),
          "GrassDensity": Param(1.0, "Share of the grass clumps kept (0..1)", type="Double"),
          "RockDensity": Param(1.0, "Multiplies the rock cluster density", type="Double"),
          "DebrisDensity": Param(1.0, "Multiplies the dead wood density", type="Double"),
          "Extent": Param(135000.0, "Half size of the square that is planted (cm)", type="Double"),
          "DetailHalf": Param(WORLD_HALF_CM, "Half size of the square with full ground detail (cm)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Trees", "Shrubs", "Grass", "Ground", "Debris", "Rocks", "Summary")
TREE_CELL = 450.0
SHRUB_CELL = 300.0
DEBRIS_CELL = 900.0
ROCK_CELL = 2200.0
GROUND_CELL = 210.0
CARPET_CELL = 130.0
FAR_GROUND_CELL = 900.0
TAGS = {"tree": "Tree", "shrub": "Shrub", "grass": "Grass", "ground": "GroundPlant", "debris": "Debris", "rock": "Rock"}
PINS = {"tree": "Trees", "shrub": "Shrubs", "grass": "Grass", "ground": "Ground", "debris": "Debris", "rock": "Rocks"}


def _summary(**kw):
    base = {"trees": 0, "shrubs": 0, "grass": 0, "ground": 0, "debris": 0, "rocks": 0, "instances": 0,
            "species_used": 0, "alder_share_riparian": 0.0, "alder_share_all": 0.0}
    base.update({"comm_" + c: 0 for c in ecology.COMMUNITIES})
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def _empty():
    out = {pin: [] for pin in PINS.values()}
    out["Summary"] = _summary()
    return out


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    if not sets:
        return _empty()
    up = inputs.get("Upstream", [])
    ex = scatter.upstream_exclusions(up)
    footprints = [v.outer for v, tags in up if isinstance(v, Polygon) and "Footprint" in tags]
    fields = [v.outer for v, tags in up if isinstance(v, Polygon) and "Field" in tags]
    roads = [(rd["pts"], 0.5 * rd["width"]) for rd in road_rows(up)]
    river = [(r[0], r[1], r[2], r[3]) for r in river_rows(up)]
    rng, seed = ctx.rng, ctx.seed
    half = (lat.n - 1) * lat.s / 2.0
    e = min(params["Extent"], half)
    F = ecology.Fields(lat, ex, footprints, seed, e)
    cx, cy = F.cx, F.cy
    G = grow.Grower(F, rng, seed)
    G.grass_share = min(1.0, max(0.0, params["GrassDensity"]))

    def box(cell, h=e):
        return scatter.jittered(cx - h, cy - h, cx + h, cy + h, cell, rng)
    G.rocks(box(ROCK_CELL), params["RockDensity"])
    G.canopy(box(TREE_CELL), params["Density"])
    G.understory(box(SHRUB_CELL), params["ShrubDensity"])
    G.hedgerows(fields, roads)
    G.tree_floor()
    G.debris(box(DEBRIS_CELL), params["DebrisDensity"])
    G.river_banks(river)
    d = min(params["DetailHalf"], e)
    gd = params["GroundDensity"]
    G.ground(box(GROUND_CELL, d), gd)
    G.carpet(box(CARPET_CELL, d), gd)
    far = ((x, y) for x, y in box(FAR_GROUND_CELL) if abs(x - cx) > d or abs(y - cy) > d)
    G.ground(far, gd)

    comm = {c: 0 for c in ecology.COMMUNITIES}
    for c in F.comm:
        if c is not None:
            comm[c] += 1
    trees = G.rows["tree"]

    def riparian(row):
        k = F.at(row[0][0], row[0][1])
        return k is not None and F.comm[k] == "riparian"
    rip = [r for r in trees if riparian(r)]
    n = {layer: len(rows) for layer, rows in G.rows.items()}
    summary = dict(trees=n["tree"], shrubs=n["shrub"], grass=n["grass"], ground=n["ground"], debris=n["debris"],
                   rocks=n["rock"], instances=sum(n.values()), species_used=sum(1 for v in G.counts.values() if v),
                   alder_share_riparian=sum(r[3] in ALDERS for r in rip) / len(rip) if rip else 0.0,
                   alder_share_all=sum(r[3] in ALDERS for r in trees) / len(trees) if trees else 0.0,
                   **{"comm_" + c: v for c, v in comm.items()})
    ctx.notes.append("%d instances: %s; %d species" % (summary["instances"], n, summary["species_used"]))
    ctx.notes.append("species " + ", ".join("%s %d" % kv for kv in sorted(G.counts.items())))
    out = {"Summary": _summary(**summary)}
    for layer, pin in PINS.items():
        rows = G.rows[layer]
        out[pin] = [(WP.mesh_points(rows), [TAGS[layer]])] if rows else []
    return out
