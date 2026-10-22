"""PyWorld W6 -- settlements (视频步骤 6：平整地形、内部路网连到最近道路、从中心向外分区、建筑规则表).

Largest first, each location gets: a platform (a plane fitted to its ground, slope clamped to MaxPlatformSlope,
kept off the roads and the river), a plaza (towns and villages), radial streets in the directions free of roads
(and a ring street in towns), the church (with its bell tower) and town hall facing the plaza, and plots along the
streets and the roads through it, typed by zone from the rule table (core: shops and houses, residential: houses,
outskirts: farmhouses with a field behind, barns, sheds). Each plot is padded flat; the road corridors are restored
on top. Footprints go to four grammar nodes by height group; foundations, pitched roofs, the spire, street modules
and plaza tiles are meshes."""
import math

from pypcg.geo import Points, Polygon, Spline
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, ROAD_INNER, geom, points as WP, rules, settle, terraform as T

STAGE = 106
RECORD = "w06"
DOC = """PyWorld W6 Settlements (聚落): platforms, plazas, streets, zones and plots from the building rule table;
footprints to the building grammar by height group, plus foundations, roofs, spires, street modules and plaza tiles."""
RANDOM = True
PARAMS = {"MaxPlatformSlope": Param(4.0, "Steepest slope a settlement platform keeps (degrees)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "FootprintsLow", "FootprintsMid", "FootprintsHigh", "FootprintsTower", "Parts", "Buildings",
           "Streets", "Areas", "Summary")
TYPES = {"Kind": "String", "Group": "String", "Settlement": "Int32", "W": "Double", "D": "Double", "Yaw": "Double",
         "Height": "Double"}


def _h(lat, x, y, fallback=0.0):
    h = lat.height(x, y) if lat.n else None
    return h if h is not None else fallback


def keep_fn(road_idx, river_idx):
    """1 away from roads and the river, 0 on their corridors: where the platform may work."""
    def keep(x, y):
        w = 1.0
        hit = road_idx.nearest(x, y, 3000.0)
        if hit is not None:
            hw = road_idx.payload(hit[1])
            w *= T.smoothstep(hw + ROAD_INNER, hw + 2000.0, hit[0])
        hit = river_idx.nearest(x, y, 5000.0)
        if hit is not None:
            half = 0.5 * river_idx.payload(hit[1])
            w *= T.smoothstep(half + 1000.0, half + 3000.0, hit[0])
        return w
    return keep


def roof(b, top):
    """A cube turned 45 degrees about the ridge: its upper half is a pitched roof over the shorter span."""
    length, span, ry = (b["w"], b["d"], b["yaw"]) if b["w"] >= b["d"] else (b["d"], b["w"], b["yaw"] + 90.0)
    side = (span + 60.0) / math.sqrt(2.0)
    return ((b["x"], b["y"], top), (0.0, ry, 45.0), ((length + 60.0) / 100.0, side / 100.0, side / 100.0), MESH["Cube"])


def street_modules(pts3):
    rows = []
    for a, b in zip(pts3, pts3[1:]):
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        rows.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2 + 2.0),
                     (math.degrees(math.atan2(b[2] - a[2], length)), geom.yaw_deg(a, b), 0.0),
                     (length / 160.0 * 1.02, 2.0 * settle.STREET_HW / 300.0, 1.0), MESH["Path"]))
    return rows


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    up = inputs.get("Upstream", [])
    locs = sorted((r for v in WP.values_tagged(inputs, "Upstream", "Location") for r in WP.rows_of(v)),
                  key=lambda r: (-r["Radius"], r["Id"]))
    roads = road_rows(up)
    river = [(r[0], r[1], r[2], r[3]) for r in river_rows(up)]
    road_idx, river_idx = geom.SegmentIndex(2000.0), geom.SegmentIndex(2000.0)
    for rd in roads:
        road_idx.add_polyline([p[:2] for p in rd["pts"]], 0.5 * rd["width"])
    for a, b in zip(river, river[1:]):
        river_idx.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
    site = settle.Site([{"pts": rd["pts"], "hw": 0.5 * rd["width"]} for rd in roads], river, geom.RingIndex())
    keep = keep_fn(road_idx, river_idx)
    plans, parts, street_tables = [], [], []
    for r in locs:
        cx, cy, rad = r["loc"][0], r["loc"][1], r["Radius"]
        plan = settle.layout({"id": r["Id"], "kind": r["Kind"], "x": cx, "y": cy, "radius": rad}, ctx.rng, site)
        plans.append(plan)
        if lat.n:
            T.platform(lat, cx, cy, rad, T.fit_plane(lat, cx, cy, rad, params["MaxPlatformSlope"]), keep)
        for st in plan["streets"]:
            zs = geom.moving_average([_h(lat, x, y) for x, y in st], 3)
            pts3 = [(x, y, z) for (x, y), z in zip(st, zs)]
            if lat.n:
                T.flatten_corridor(lat, [(x, y, z, settle.STREET_HW, False) for x, y, z in pts3], 100.0, 400.0)
            parts += street_modules(pts3)
            cum = geom.cumulative(st)
            street_tables.append(([{"loc": p, "Width": 2.0 * settle.STREET_HW, "S": s} for p, s in zip(pts3, cum)]))
        if plan["plaza"]:
            zc = _h(lat, cx, cy)
            if lat.n:
                T.pad(lat, geom.circle(cx, cy, settle.PLAZA_R, 32), zc, 200.0, 600.0)
            plan["plaza_z"] = zc
            for gy in range(-12, 13):
                for gx in range(-12, 13):
                    if math.hypot(150.0 * gx, 150.0 * gy) <= settle.PLAZA_R - 75.0:
                        parts.append(((cx + 150.0 * gx, cy + 150.0 * gy, zc + 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                                      MESH["Tile"]))
        for b in plan["buildings"]:
            zs = [z for z in (lat.height(x, y) if lat.n else None for x, y in b["ring"] + [(b["x"], b["y"])])
                  if z is not None]
            b["z"] = sum(zs) / len(zs) if zs else 0.0
            if lat.n:
                T.pad(lat, b["ring"], b["z"], 200.0, 400.0)
    if lat.n:
        for rd in sorted(roads, key=lambda r: r["cls"] != "Secondary"):
            T.flatten_corridor(lat, [(p[0], p[1], p[2], 0.5 * rd["width"], br) for p, br in zip(rd["pts"], rd["bridge"])])
        # Lock every footprint (+1 m) at its pad height last: a neighbour's pad blend or a street would otherwise tilt it.
        for plan in plans:
            for b in plan["buildings"]:
                T.pad(lat, b["ring"], b["z"], 100.0, 0.0)
    feet = {g: [] for g in rules.GROUPS}
    rows, areas, check = [], [], geom.RingIndex()
    per, overlaps, on_road = {}, 0, 0
    for plan in plans:
        per[plan["id"]] = {"kind": plan["kind"], "n": len(plan["buildings"]),
                           "churches": sum(b["kind"] == "Church" for b in plan["buildings"])}
        for b in plan["buildings"]:
            top = b["z"] + rules.WALL_TOP[b["group"]]
            ring3 = [(x, y, b["z"]) for x, y in b["ring"]]
            feet[b["group"]].append((Spline(ring3, closed=True, linear=True), ["Footprint", b["group"]]))
            areas.append((Polygon(list(b["ring"]), [], b["z"]), ["Footprint"]))
            parts.append(((b["x"], b["y"], b["z"] - 90.0), (0.0, b["yaw"], 0.0),
                          ((b["w"] + 40.0) / 100.0, (b["d"] + 40.0) / 100.0, 2.2), MESH["Cube"]))
            if b["group"] == "Tower":
                parts.append(((b["x"], b["y"], top + 400.0), (0.0, b["yaw"], 0.0), (6.4, 6.4, 8.0), MESH["Cone"]))
            else:
                parts.append(roof(b, top))
            rows.append({"loc": (b["x"], b["y"], b["z"]), "Kind": b["kind"], "Group": b["group"],
                         "Settlement": b["settlement"], "W": b["w"], "D": b["d"], "Yaw": b["yaw"],
                         "Height": rules.HEIGHT[b["group"]]})
            overlaps += check.overlaps(b["ring"])
            check.add(b["ring"])
            # on a road, a street (any settlement's) or in the river
            on_road += any(site.near_line(x, y, 0.0) or site.near_river(x, y, 0.0)
                           for x, y in geom.probe_points(b["ring"], 400.0))
        if plan["plaza"]:
            areas.append((Polygon(geom.circle(plan["x"], plan["y"], settle.PLAZA_R, 32), [], plan["plaza_z"]), ["Plaza"]))
        for fr in plan["fields"]:
            areas.append((Polygon(list(fr), [], _h(lat, *geom.centroid(fr))), ["Field"]))

    def least(kind, key="n"):
        vals = [p[key] for p in per.values() if p["kind"] in kind]
        return min(vals) if vals else -1
    summary = {"buildings": len(rows), "town_min": least(("Town",)), "village_min": least(("Village",)),
               "hamlet_min": least(("Hamlet",)), "churches_min": least(("Town", "Village"), "churches"),
               "overlaps": int(overlaps), "on_road": int(on_road), "streets": len(street_tables),
               "plazas": sum(1 for p in plans if p["plaza"]), "fields": sum(len(p["fields"]) for p in plans)}
    ctx.notes.append("%d settlements, %d buildings" % (len(plans), len(rows)))
    out = {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets],
           "Parts": [(WP.mesh_points(parts), ["SettlementPart"])] if parts else [],
           "Buildings": [(WP.table_points(rows, TYPES), ["Building"])] if rows else [],
           "Streets": [(WP.table_points(t, {"Width": "Double", "S": "Double"}), ["Street"]) for t in street_tables],
           "Areas": areas, "Summary": [(WP.summary(summary), ["Summary"])]}
    for g in rules.GROUPS:
        out["Footprints" + g] = feet[g]
    return out
