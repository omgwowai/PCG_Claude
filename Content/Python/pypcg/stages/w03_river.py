"""PyWorld W3 -- the river (视频步骤 4：河流与道路同一套寻路模型，只是容差不同).

A* from the river source to the outlet on every second terrain vertex (11.7 m): each step costs its length, more
the higher it lies above the lowest ground, plus a heavy price for climbing, plus a little value noise so the
river meanders; it keeps out of the inner half of every location. The path is smoothed (Chaikin) and resampled every
10 m. The water line is the running minimum of the ground along it, 80 cm under, smoothed and kept non-increasing;
the width grows from WidthStart to WidthEnd. The channel is carved into the terrain (bed `Depth` under the water,
banks at 1:2), and the water surface is laid as stretched Plane meshes (MI_ocean)."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.world import MESH, VERTEX_CM, astar, geom, noise, points as WP, terraform as T
from pypcg.world.grid import Lattice

STAGE = 103
RECORD = "w03"
DOC = """PyWorld W3 River (河流): A* from the source to the outlet along low ground, smoothed; the water line falls
monotonically, the width grows downstream; the channel is carved into the terrain and the water surface placed."""
RANDOM = True
PARAMS = {
    "WidthStart": Param(600.0, "River width at the source (cm)", type="Double"),
    "WidthEnd": Param(2000.0, "River width at the outlet (cm)", type="Double"),
    "Depth": Param(150.0, "Bed depth under the water at the centre line (cm)", type="Double"),
    "Meander": Param(0.6, "Strength of the noise that makes the river wander", type="Double"),
    "TownAvoid": Param(20.0, "Extra cost per cm inside the inner half of a location", type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "River", "Water", "Summary")
GRID_HALF = 140000.0
STEP = 1000.0
WATER_UNDER = 80.0


def river_rows(items):
    """[(x, y, water, width, bed, s)] of every `River` point table, ordered by S."""
    rows = []
    for v, tags in items:
        if isinstance(v, Points) and "River" in tags:
            for r in WP.rows_of(v):
                rows.append((r["loc"][0], r["loc"][1], r["WaterZ"], r["Width"], r["BedZ"], r["S"]))
    return sorted(rows, key=lambda r: r[5])


def terrain_sets(items):
    """(lattice, [(points, ks)]) over every point set on the pin."""
    sets = [v for v, _t in items if isinstance(v, Points) and len(v)]
    locs = [p for v in sets for p in v.loc]
    lat, ks = Lattice.from_locs(locs, VERTEX_CM)
    out, at = [], 0
    for v in sets:
        out.append((v, ks[at:at + len(v)]))
        at += len(v)
    return lat, out


def _summary(**kw):
    base = {"length_m": 0.0, "samples": 0, "carved": 0, "monotone": False, "width_min_cm": 0.0, "width_max_cm": 0.0,
            "water_drop_cm": 0.0}
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    up = inputs.get("Upstream", [])
    ends = [r for v in WP.values_tagged(inputs, "Upstream", "RiverEnd") for r in WP.rows_of(v)]
    locs = [(r["loc"][0], r["loc"][1], r["Radius"]) for v in WP.values_tagged(inputs, "Upstream", "Location")
            for r in WP.rows_of(v)]
    terrain_out = lambda: [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets]
    src = next((r["loc"] for r in ends if r["Role"] == "Source"), None)
    dst = next((r["loc"] for r in ends if r["Role"] == "Outlet"), None)
    if not sets or src is None or dst is None:
        ctx.notes.append("no terrain or no river ends (%d upstream items)" % len(up))
        return {"Terrain": terrain_out(), "River": [], "Water": [], "Summary": _summary()}
    co = lat.coarse(2, GRID_HALF)
    ka, kb = co.nearest_valid(src[0], src[1]), co.nearest_valid(dst[0], dst[1])
    zmin = min(z for z in co.z if z is not None)
    seed, meander, avoid = ctx.seed, params["Meander"], params["TownAvoid"]

    def cost(a, b, length):
        za, zb = co.z[a], co.z[b]
        x, y = co.xy(b)
        c = length * (1.0 + (zb - zmin) / 800.0 + meander * noise.value(x / 40000.0, y / 40000.0, seed + 5))
        c += 60.0 * max(0.0, zb - za)
        for lx, ly, lr in locs:
            if math.hypot(x - lx, y - ly) < 0.5 * lr:
                c += length * avoid
        return c
    path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES8) if ka is not None and kb is not None else None
    if not path or len(path) < 2:
        ctx.notes.append("no river path")
        return {"Terrain": terrain_out(), "River": [], "Water": [], "Summary": _summary()}
    pts = geom.resample(geom.chaikin([co.xy(k) for k in path], 3), STEP)
    ground, last = [], None
    for x, y in pts:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    water = []
    for g in ground:
        water.append(min(water[-1], g - WATER_UNDER) if water else g - WATER_UNDER)
    water = geom.moving_average(water, 6)
    for i in range(1, len(water)):
        water[i] = min(water[i], water[i - 1])
    cum = geom.cumulative(pts)
    total = cum[-1]
    ws, we, depth = params["WidthStart"], params["WidthEnd"], params["Depth"]
    width = [ws + (we - ws) * (s / total if total else 0.0) for s in cum]
    carved = T.carve_river(lat, [(p[0], p[1], w, wd) for p, w, wd in zip(pts, water, width)], depth)
    rows = [{"loc": (p[0], p[1], w), "Width": wd, "WaterZ": w, "BedZ": w - depth, "S": s}
            for p, w, wd, s in zip(pts, water, width, cum)]
    planes = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = geom.dist2d(a, b)
        planes.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (water[i] + water[i + 1]) / 2 + 5.0),
                       (0.0, geom.yaw_deg(a, b), 0.0),
                       (length * 1.15 / 100.0, (width[i] + width[i + 1]) / 200.0, 1.0), MESH["Plane"]))
    types = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}
    ctx.notes.append("river %.0f m, %d vertices carved" % (total / 100.0, carved))
    return {"Terrain": terrain_out(), "River": [(WP.table_points(rows, types), ["River"])],
            "Water": [(WP.mesh_points(planes), ["Water"])],
            "Summary": _summary(length_m=total / 100.0, samples=len(pts), carved=carved,
                                monotone=all(b <= a + 1e-9 for a, b in zip(water, water[1:])),
                                width_min_cm=min(width), width_max_cm=max(width), water_drop_cm=water[0] - water[-1])}
