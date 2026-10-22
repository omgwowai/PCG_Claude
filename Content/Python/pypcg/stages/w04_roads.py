"""PyWorld W4 -- the road network (视频步骤 3).

A* on every second terrain vertex with 16 directions (the video's "look in more directions" trick, so roads follow
the terrain instead of zigzagging): a step costs its length x (1 + 6 (grade / MainGrade)^2), steps steeper than
HardGrade are blocked, river cells cost WaterPenalty times more (short, square crossings) and cells already on a
road cost ReuseFactor times less (new roads join the network). The trunk joins the south exit, the towns and
villages by y and the north exit; every hamlet then joins the nearest road (multi-goal Dijkstra). Each road is
smoothed and resampled every 5 m; its profile is the ground averaged over 60 m, cut and filled to the class's grade,
raised to the water + 2.5 m on bridges (ramps keep the grade). The corridor is flattened to the profile except on
bridge spans, and lane meshes are laid every 5 m."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.world import MESH, astar, geom, points as WP, terraform as T

STAGE = 104
RECORD = "w04"
DOC = """PyWorld W4 Roads (道路): 16-direction A* with grade, water and reuse costs; trunk through the exits, towns
and villages, hamlets joined to the network; graded profiles with bridges over the river; flattened corridors and
lane meshes."""
RANDOM = False
PARAMS = {
    "MainWidth": Param(800.0, "Main road width (cm)", type="Double"),
    "SecondaryWidth": Param(550.0, "Secondary road width (cm)", type="Double"),
    "MainGrade": Param(0.10, "Maximum grade of the main roads", type="Double"),
    "SecondaryGrade": Param(0.14, "Maximum grade of the secondary roads", type="Double"),
    "HardGrade": Param(0.22, "Steps steeper than this are impassable", type="Double"),
    "WaterPenalty": Param(6.0, "Cost multiplier of a step into the river", type="Double"),
    "ReuseFactor": Param(0.35, "Cost multiplier of a step along an existing road", type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Roads", "Modules", "Summary")
GRID_HALF = 100000.0
STEP = 500.0
BRIDGE_CLEAR = 250.0
BRIDGE_REACH = 400.0
TYPES = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def road_rows(items):
    """[dict(id, cls, width, pts [(x, y, z)], bridge [bool])] of every `Road` table, by RoadId."""
    out = []
    for v, tags in items:
        if isinstance(v, Points) and "Road" in tags and len(v):
            rows = sorted(WP.rows_of(v), key=lambda r: r["S"])
            out.append({"id": rows[0]["RoadId"], "cls": rows[0]["Class"], "width": rows[0]["Width"],
                        "pts": [r["loc"] for r in rows], "bridge": [bool(r["Bridge"]) for r in rows]})
    return sorted(out, key=lambda r: r["id"])


def river_index(rows):
    idx = geom.SegmentIndex(2000.0)
    for a, b in zip(rows, rows[1:]):
        idx.add(a[:2], b[:2], (0.5 * (a[2] + b[2]), 0.5 * (a[3] + b[3])))
    return idx


def water_at(idx, x, y, extra):
    """The water z when (x, y) is within half the river's width + extra, else None."""
    hit = idx.nearest(x, y, 3000.0 + extra)
    if hit is None:
        return None
    water, width = idx.payload(hit[1])
    return water if hit[0] < 0.5 * width + extra else None


def _clamp(z, ds, g):
    for i in range(1, len(z)):
        z[i] = min(max(z[i], z[i - 1] - g * ds[i - 1]), z[i - 1] + g * ds[i - 1])
    for i in range(len(z) - 2, -1, -1):
        z[i] = min(max(z[i], z[i + 1] - g * ds[i]), z[i + 1] + g * ds[i])


def _raise(z, ds, g):
    for i in range(1, len(z)):
        z[i] = max(z[i], z[i - 1] - g * ds[i - 1])
    for i in range(len(z) - 2, -1, -1):
        z[i] = max(z[i], z[i + 1] - g * ds[i])


def profile(pts, lat, grade, waters, anchor=None):
    """The road's z: ground averaged over +-30 m, cut/filled to `grade`, bridges raised to water + BRIDGE_CLEAR with
    graded ramps; `anchor` pins the last point (a branch meeting the trunk)."""
    ground, last = [], None
    for x, y in pts:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    z = geom.moving_average(ground, 6)
    ds = [geom.dist2d(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if anchor is not None:
        z[-1] = anchor
    _clamp(z, ds, grade)
    for i, w in enumerate(waters):
        if w is not None:
            z[i] = max(z[i], w + BRIDGE_CLEAR)
    _raise(z, ds, grade)
    return z


def max_grade(pts, z):
    g = 0.0
    for i in range(len(pts) - 1):
        d = geom.dist2d(pts[i], pts[i + 1])
        if d > 1.0:
            g = max(g, abs(z[i + 1] - z[i]) / d)
    return g


def modules(pts, z, cls, width):
    rows = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        yaw = geom.yaw_deg(a, b)
        rot = (math.degrees(math.atan2(z[i + 1] - z[i], length)), yaw, 0.0)
        mx, my, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (z[i] + z[i + 1]) / 2 + 2.0
        nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
        if cls == "Main":
            for off in (-200.0, 200.0):
                rows.append(((mx + nx * off, my + ny * off, mz), rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["LaneCar"]))
            rows.append(((mx, my, mz + 1.0), rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["Divider"]))
        else:
            rows.append(((mx, my, mz), rot, (length / 160.0 * 1.02, width / 300.0, 1.0), MESH["Path"]))
    return rows


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    locs = [r for v in WP.values_tagged(inputs, "Upstream", "Location") for r in WP.rows_of(v)]
    exits = sorted((r["loc"] for v in WP.values_tagged(inputs, "Upstream", "RoadExit") for r in WP.rows_of(v)),
                   key=lambda p: p[1])
    river = river_rows(inputs.get("Upstream", []))
    if not sets or len(exits) + len(locs) < 2:
        return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets], "Roads": [], "Modules": [],
                "Summary": [(WP.summary({"roads": 0, "main_roads": 0, "secondary_roads": 0, "length_m": 0.0,
                                         "max_grade_main": 0.0, "max_grade_secondary": 0.0, "bridge_samples": 0,
                                         "connected": False, "unreachable": 0}), ["Summary"])]}
    co = lat.coarse(2, GRID_HALF)
    ridx = river_index(river)
    water_cells = {k for k in range(len(co.z)) if co.z[k] is not None and water_at(ridx, *co.xy(k), 500.0) is not None}
    road_cells = set()
    p = params

    def cost(a, b, length):
        g = abs(co.z[b] - co.z[a]) / length
        if g > p["HardGrade"]:
            return None
        c = length * (1.0 + 6.0 * (g / p["MainGrade"]) ** 2)
        if b in water_cells:
            c *= p["WaterPenalty"]
        if b in road_cells:
            c *= p["ReuseFactor"]
        return c
    trunk = [exits[0]] if exits else []
    trunk += [r["loc"] for r in sorted(locs, key=lambda r: r["loc"][1]) if r["Kind"] != "Hamlet"]
    trunk += [exits[-1]] if len(exits) > 1 else []
    routes, unreachable = [], 0
    for a, b in zip(trunk, trunk[1:]):
        ka, kb = co.nearest_valid(a[0], a[1]), co.nearest_valid(b[0], b[1])
        path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES16, h_scale=p["ReuseFactor"]) if ka is not None and kb is not None else None
        if path is None:
            unreachable += 1
            continue
        road_cells.update(path)
        routes.append(("Main", path))
    for r in sorted((r for r in locs if r["Kind"] == "Hamlet"), key=lambda r: -r["Radius"]):
        ka = co.nearest_valid(r["loc"][0], r["loc"][1])
        path = astar.search(co, {ka: 0.0}, road_cells, cost, astar.MOVES16, h_scale=0.0) if ka is not None and road_cells else None
        if path is None:
            unreachable += 1
            continue
        road_cells.update(path)
        routes.append(("Secondary", path))
    # connectivity: routes sharing a cell are joined
    parent = list(range(len(routes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner = {}
    for i, (_c, path) in enumerate(routes):
        for k in path:
            if k in owner:
                parent[find(i)] = find(owner[k])
            owner[k] = i
    connected = unreachable == 0 and len({find(i) for i in range(len(routes))}) <= 1
    roads, built = [], geom.SegmentIndex(2000.0)
    for rid, (cls, path) in enumerate(routes):
        if len(path) < 2:
            continue
        pts = geom.resample(geom.chaikin([co.xy(k) for k in path], 2), STEP)
        waters = [water_at(ridx, x, y, BRIDGE_REACH) for x, y in pts]
        anchor = None
        if cls == "Secondary":
            hit = built.nearest(pts[-1][0], pts[-1][1], 5000.0)
            anchor = built.payload(hit[1]) if hit else None
        grade = p["MainGrade"] if cls == "Main" else p["SecondaryGrade"]
        z = profile(pts, lat, grade, waters, anchor)
        for i in range(len(pts) - 1):
            built.add(pts[i], pts[i + 1], 0.5 * (z[i] + z[i + 1]))
        width = p["MainWidth"] if cls == "Main" else p["SecondaryWidth"]
        roads.append({"id": rid, "cls": cls, "width": width, "pts": pts, "z": z, "bridge": [w is not None for w in waters]})
    for rd in sorted(roads, key=lambda r: r["cls"] != "Secondary"):        # secondaries first, the trunk on top
        T.flatten_corridor(lat, [(x, y, z, 0.5 * rd["width"], br) for (x, y), z, br in zip(rd["pts"], rd["z"], rd["bridge"])])
    out_roads, mods, length, grades = [], [], 0.0, {"Main": 0.0, "Secondary": 0.0}
    for rd in roads:
        cum = geom.cumulative(rd["pts"])
        length += cum[-1]
        grades[rd["cls"]] = max(grades[rd["cls"]], max_grade(rd["pts"], rd["z"]))
        rows = [{"loc": (x, y, z), "RoadId": rd["id"], "Class": rd["cls"], "Width": rd["width"], "Bridge": br, "S": s}
                for (x, y), z, br, s in zip(rd["pts"], rd["z"], rd["bridge"], cum)]
        out_roads.append((WP.table_points(rows, TYPES), ["Road", rd["cls"]]))
        mods.extend(modules(rd["pts"], rd["z"], rd["cls"], rd["width"]))
    summary = {"roads": len(roads), "main_roads": sum(r["cls"] == "Main" for r in roads),
               "secondary_roads": sum(r["cls"] == "Secondary" for r in roads), "length_m": length / 100.0,
               "max_grade_main": grades["Main"], "max_grade_secondary": grades["Secondary"],
               "bridge_samples": sum(sum(r["bridge"]) for r in roads), "connected": bool(connected),
               "unreachable": unreachable}
    ctx.notes.append("%d roads, %.0f m, %d unreachable" % (len(roads), length / 100.0, unreachable))
    return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets], "Roads": out_roads,
            "Modules": [(WP.mesh_points(mods), ["RoadModule"])] if mods else [],
            "Summary": [(WP.summary(summary), ["Summary"])]}
