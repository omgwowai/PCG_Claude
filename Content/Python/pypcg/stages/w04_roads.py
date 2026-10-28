"""PyWorld W4 -- the road network (视频步骤 3；路网按 Galin 2010/2011 与育碧 Wildlands 的做法：代价场 + 复用并入路网).

A* on every second terrain vertex with 16 directions (the video's "look in more directions" trick, so roads follow
the terrain instead of zigzagging): a step costs its length x (1 + 6 (grade / MainGrade)^2) x a low-frequency
preference field (Wander: soil, fields, property lines -- over flat ground it is what bends a country road), steps
steeper than HardGrade are blocked, river cells cost WaterPenalty times more (short, square crossings), the 20 m beside
the river RiverShy more (roads keep off the riverside), and cells already on a road cost ReuseFactor times less (new
roads join the network). The trunk joins the south exit, the towns and villages by y and the north exit; every hamlet
then joins the nearest road (multi-goal Dijkstra). A route that meets the network is cut into the pieces off it: it
ends at a T or Y junction instead of running along the road it found. Each piece's junction ends are moved onto the
road it joins, then the piece is smoothed (Gaussian, 25 m main / 15 m secondary, ends pinned) and resampled every 5 m;
its profile is the ground averaged over 60 m, cut and filled to the class's grade with its junction ends at the joined
road's height, raised to the water + 2.5 m on bridges (ramps keep the grade). The corridor is flattened to the profile
except on bridge spans, and lane meshes are laid every 5 m."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.world import MESH, astar, geom, noise, points as WP, terraform as T

STAGE = 104
RECORD = "w04"
DOC = """PyWorld W4 Roads (道路): 16-direction A* with grade, water and reuse costs; trunk through the exits, towns
and villages, hamlets joined to the network; graded profiles with bridges over the river; flattened corridors and
lane meshes."""
RANDOM = True                    # the preference field is drawn from the seed
PARAMS = {
    "MainWidth": Param(800.0, "Main road width (cm)", type="Double"),
    "SecondaryWidth": Param(550.0, "Secondary road width (cm)", type="Double"),
    "MainGrade": Param(0.10, "Maximum grade of the main roads", type="Double"),
    "SecondaryGrade": Param(0.14, "Maximum grade of the secondary roads", type="Double"),
    "HardGrade": Param(0.22, "Steps steeper than this are impassable", type="Double"),
    "WaterPenalty": Param(6.0, "Cost multiplier of a step into the river", type="Double"),
    "ReuseFactor": Param(0.35, "Cost multiplier of a step along an existing road", type="Double"),
    "Wander": Param(0.5, "Strength of the low-frequency preference field that bends roads over flat ground (0: "
                         "straight)", type="Double"),
    "RiverShy": Param(2.0, "Cost multiplier of a step within 20 m of the river bank", type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Roads", "Modules", "Summary")
GRID_HALF = 100000.0
STEP = 500.0
BRIDGE_CLEAR = 250.0
BRIDGE_REACH = 400.0
WANDER_CM = 30000.0              # the preference field's scale
MERGE_TURN = 75.0                # degrees: the trunk runs on through a place unless it turns more
SMOOTH_CM = {"Main": 6000.0, "Secondary": 3000.0}   # Gaussian sigma: a right angle becomes a ~sigma radius curve
LANE_LIFT = 8.0                  # lane meshes (0..20 cm thick) sit this far above the written terrain
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


def profile(pts, lat, grade, waters, anchor=None, start=None):
    """The road's z: ground averaged over +-30 m, cut/filled to `grade`, bridges raised to water + BRIDGE_CLEAR with
    graded ramps; `anchor` pins the last point and `start` the first (junctions with the roads they join)."""
    ground, last = [], None
    for x, y in pts:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    z = geom.moving_average(ground, 6)
    ds = [geom.dist2d(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if anchor is not None:
        z[-1] = anchor
    if start is not None:
        z[0] = start
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


def modules(pts, z, cls, width, bridge=None, ground=None):
    """Lane meshes every segment. Off bridges each lane module takes the ground under its own two ends (`ground(x, y)`,
    the terrain as written) so it shows wherever corridors meet; on a bridge span it takes the profile `z`."""
    rows = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        yaw = geom.yaw_deg(a, b)
        nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
        on_bridge = bridge is not None and (bridge[i] or bridge[i + 1])

        def lane(off):
            za, zb = z[i], z[i + 1]
            if ground is not None and not on_bridge:
                ha = ground(a[0] + nx * off, a[1] + ny * off)
                hb = ground(b[0] + nx * off, b[1] + ny * off)
                hm = ground((a[0] + b[0]) / 2 + nx * off, (a[1] + b[1]) / 2 + ny * off)
                if ha is not None and hb is not None:
                    za, zb = ha, hb
                    if hm is not None and hm > (za + zb) / 2:      # the ground bulges between the ends: lift
                        za, zb = za + hm - (za + zb) / 2, zb + hm - (za + zb) / 2
            return (((a[0] + b[0]) / 2 + nx * off, (a[1] + b[1]) / 2 + ny * off, (za + zb) / 2 + LANE_LIFT),
                    (math.degrees(math.atan2(zb - za, length)), yaw, 0.0))
        if cls == "Main":
            for off in (-200.0, 200.0):
                loc, rot = lane(off)
                rows.append((loc, rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["LaneCar"]))
            loc, rot = lane(0.0)
            rows.append(((loc[0], loc[1], loc[2] + 1.0), rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["Divider"]))
        else:
            loc, rot = lane(0.0)
            rows.append((loc, rot, (length / 160.0 * 1.02, width / 300.0, 1.0), MESH["Path"]))
    return rows


def off_network(path, network):
    """The pieces of an A* path that are off the existing network, each with the network cell it touches at either
    end: a route that meets a road joins it there (a T or Y junction) instead of running along it."""
    pieces, cur = [], []
    for k in path:
        if k in network:
            if cur:
                pieces.append(cur + [k])
            cur = [k]
        else:
            cur.append(k)
    if len(cur) > 1 or (cur and cur[0] not in network):
        pieces.append(cur)
    return [q for q in pieces if len(q) >= 2 and not all(k in network for k in q)]


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
    shy_cells = {k for k in range(len(co.z)) if co.z[k] is not None and k not in water_cells
                 and water_at(ridx, *co.xy(k), 2500.0) is not None}
    road_cells = set()
    p = params
    wander = p["Wander"]
    pref = [None if z is None else math.exp(wander * noise.fbm(co.xy(k)[0] / WANDER_CM, co.xy(k)[1] / WANDER_CM,
                                                               ctx.seed + 71, 2)) for k, z in enumerate(co.z)]
    h_min = math.exp(-wander)                          # the cheapest cost per cm: the admissible heuristic's scale

    def cost(a, b, length):
        g = abs(co.z[b] - co.z[a]) / length
        if g > p["HardGrade"]:
            return None
        c = length * (1.0 + 6.0 * (g / p["MainGrade"]) ** 2)
        if b in road_cells:                            # the network is the network: no preference along it
            return c * p["ReuseFactor"]
        c *= pref[b]
        if b in water_cells:
            c *= p["WaterPenalty"]
        elif b in shy_cells:
            c *= p["RiverShy"]
        return c
    trunk = [exits[0]] if exits else []
    trunk += [r["loc"] for r in sorted(locs, key=lambda r: r["loc"][1]) if r["Kind"] != "Hamlet"]
    trunk += [exits[-1]] if len(exits) > 1 else []
    routes, unreachable = [], 0
    legs = []
    for a, b in zip(trunk, trunk[1:]):
        ka, kb = co.nearest_valid(a[0], a[1]), co.nearest_valid(b[0], b[1])
        path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES16, h_scale=min(h_min, p["ReuseFactor"])) if ka is not None and kb is not None else None
        if path is None:
            unreachable += 1
        else:
            road_cells.update(path)                    # a later leg may run along this one (then joins it there)
        legs.append(path)
    # consecutive legs are one road through the places they link (smoothed as a whole: no corner at a town centre),
    # unless the trunk doubles back there (a turn over MERGE_TURN would smooth into a hairpin)
    def heading(a, b):
        (ax, ay), (bx, by) = co.xy(a), co.xy(b)
        return math.atan2(by - ay, bx - ax)
    chain, flushed = [], set()
    for path in legs + [None]:
        if path is not None and chain and chain[-1] == path[0] and len(chain) > 4 and len(path) > 4:
            turn = abs((heading(path[0], path[4]) - heading(chain[-5], chain[-1]) + math.pi) % (2.0 * math.pi) - math.pi)
            if turn < math.radians(MERGE_TURN):
                chain += path[1:]
                continue
        if chain:
            routes.extend(("Main", piece) for piece in off_network(chain, flushed))
            flushed.update(chain)
        chain = list(path) if path is not None else []
    for r in sorted((r for r in locs if r["Kind"] == "Hamlet"), key=lambda r: -r["Radius"]):
        ka = co.nearest_valid(r["loc"][0], r["loc"][1])
        path = astar.search(co, {ka: 0.0}, road_cells, cost, astar.MOVES16, h_scale=0.0) if ka is not None and road_cells else None
        if path is None:
            unreachable += 1
            continue
        routes.extend(("Secondary", piece) for piece in off_network(path, road_cells))
        road_cells.update(path)
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
    roads, built, junction_cells = [], geom.SegmentIndex(2000.0), set()
    for rid, (cls, path) in enumerate(routes):
        if len(path) < 2:
            continue
        raw = [co.xy(k) for k in path]
        # a junction end (a cell already on an earlier piece) moves onto that road's built centre line, at its height
        ends = [None, None]
        for e, k in ((0, path[0]), (1, path[-1])):
            if k in junction_cells:
                hit = built.nearest(raw[-e][0], raw[-e][1], 3000.0)
                if hit is not None:
                    (ax, ay), (bx, by) = built.segment(hit[1])
                    za, zb = built.payload(hit[1])
                    t = hit[2]
                    raw[-e] = (ax + (bx - ax) * t, ay + (by - ay) * t)
                    ends[e] = za + (zb - za) * t
        pts = geom.smooth_polyline(raw, SMOOTH_CM[cls], STEP)
        if len(pts) < 2:
            continue
        waters = [water_at(ridx, x, y, BRIDGE_REACH) for x, y in pts]
        grade = p["MainGrade"] if cls == "Main" else p["SecondaryGrade"]
        z = profile(pts, lat, grade, waters, ends[1], ends[0])
        for i in range(len(pts) - 1):
            built.add(pts[i], pts[i + 1], (z[i], z[i + 1]))
        junction_cells.update(path)
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
        mods.extend(modules(rd["pts"], rd["z"], rd["cls"], rd["width"], rd["bridge"], lat.height if lat.n else None))
    summary = {"roads": len(roads), "main_roads": sum(r["cls"] == "Main" for r in roads),
               "secondary_roads": sum(r["cls"] == "Secondary" for r in roads), "length_m": length / 100.0,
               "max_grade_main": grades["Main"], "max_grade_secondary": grades["Secondary"],
               "bridge_samples": sum(sum(r["bridge"]) for r in roads), "connected": bool(connected),
               "unreachable": unreachable}
    ctx.notes.append("%d roads, %.0f m, %d unreachable" % (len(roads), length / 100.0, unreachable))
    return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets], "Roads": out_roads,
            "Modules": [(WP.mesh_points(mods), ["RoadModule"])] if mods else [],
            "Summary": [(WP.summary(summary), ["Summary"])]}
