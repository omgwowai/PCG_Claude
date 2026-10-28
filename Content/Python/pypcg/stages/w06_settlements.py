"""PyWorld W6 -- settlements (视频步骤 6：平整地形、内部路网连到最近道路、从中心向外分区、建筑规则表).

Largest first, each location gets: a platform (a plane fitted to its ground, slope clamped to MaxPlatformSlope,
kept off the roads and the river), a plaza (towns and villages), organic streets, the church (with its bell tower)
and town hall facing the plaza, and plots along the streets and the roads through it, typed by zone from the rule
table (core: terraced shops and houses, residential: houses, outskirts: farmhouses with a field behind, barns,
sheds). Each plot is padded flat; the road corridors are restored on top. Every building is then assembled from the
Megascans kit by the style database (City Sample 式: style code -> vertical grammar -> per-level horizontal grammar
by wall length -> modules, corners, doors, props, hipped roof; world/building.py) and leaves as `Modules` points
(Mesh, Mat0) for the native mesh spawner; street modules and plaza tiles are `Parts`."""
import math

from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import ROAD_INNER, building, geom, kit as K, points as WP, rules, settle, terraform as T

STAGE = 106
RECORD = "w06"
DOC = """PyWorld W6 Settlements (聚落): platforms, plazas, streets, zones and plots from the building rule table; each
building assembled from the Megascans kit by its style code (facades, corners, doors, props, hipped roof) as module
points for the mesh spawner, plus street modules and plaza tiles."""
RANDOM = True
PARAMS = {"MaxPlatformSlope": Param(4.0, "Steepest slope a settlement platform keeps (degrees)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Modules", "Parts", "Buildings", "Streets", "Areas", "Summary")
STREET_PULL = 60.0           # cm a street house's floor may move from its ground towards its street
CUT_REACH = 830.0            # the ground above a floor is cut down to it this far round the footprint (a cell diagonal)
STREET_KEEP = 30.0           # the cut stops this far beyond a street's edge
PLINTH = building.PLINTH - 5.0   # how far a building's stone plinth reaches below its floor
LIFT_MAX = 35.0              # a street slab rises at most this much over its line to stay clear of the ground
SETTS_TOP = 8.0              # the setts' top over the ground under them (the sidewalks 13 cm higher): the ground fills
                             # the gaps between the stones below that, like the dirt between real setts
SLAB_GRID = 9                # a street slab's plane is fitted to (and lifted over) a 9 x 9 grid of ground heights
SETTS_Z = 10.0               # the setts' 4 cm skin (stone relief included) scaled into a 42 cm block -- more stretches
                             # the relief until the ground fills the gaps (20: only the stones' tops showed) --
WALK_Z = 5.0                 # the sidewalk's flat 20 cm slab into 1 m, so a lifted slab shows no gap under it
PLAZA_TOP = 8.0              # the plaza stones' top over the plaza's level
DOOR_PROBE = 60.0            # the ground in front of a door, for its steps: this far out from the facade's middle
OUTBUILDING_HANG = 150.0     # an outbuilding whose floor stands this far over the mean ground under it is left out
TYPES = {"Kind": "String", "Style": "String", "Settlement": "Int32", "W": "Double", "D": "Double", "Yaw": "Double",
         "Floors": "Int32", "Height": "Double", "Tint": "String", "Roof": "String", "Shop": "Bool"}


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


def street_modules(pts3, walks, ground=None, on_road=None, peaks=None):
    """The street cross-section along a street, one row of slabs per slab length (3 m, so the setts keep their size
    along the street): cobbles over the carriageway and, where walks[i], a raised sidewalk either side, its top 13 cm
    over the setts. Each slab is seated on `ground` (the final terrain: the engine's own triangulated surface) and
    `peaks(x0, y0, x1, y1)` (its vertices in a box, where that surface can peak under a slab): a plane fitted to a
    9 x 9 grid over the slab gives its pitch and roll, lifted so no ground under it comes through its top. The setts
    are a 4 cm skin at z 16..20, scaled SETTS_Z in Z into a block; the sidewalk slab (z 0..20) is scaled WALK_Z. Slabs
    pivot on a corner; each is stretched 3 % so a bend leaves no slit. Where the street runs onto a road
    (on_road(x, y)) the road's own lanes take over."""
    rows = []
    hw = settle.STREET_HW
    dense = geom.resample([(x, y, z, 1.0 if w else 0.0) for (x, y, z), w in zip(pts3, walks)], K.SLAB)
    walks = [p[3] > 0.5 for p in dense]
    grid = [q / (SLAB_GRID - 1.0) for q in range(SLAB_GRID)]
    var = sum((t - 0.5) ** 2 for t in grid) * SLAB_GRID          # sum over the grid of (t - 0.5)^2

    def at(x, y, fallback):
        h = ground(x, y) if ground is not None else None
        return fallback if h is None else h
    for i, (a, b) in enumerate(zip(dense, dense[1:])):
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = -uy, ux
        if on_road is not None and on_road(0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1])):
            continue
        za, zb = at(a[0], a[1], a[2]), at(b[0], b[1], b[2])
        yaw = geom.yaw_deg(a, b)
        sx = length * 1.03 / K.SLAB

        def slab(mesh, y0, width, top, base, sz):
            """Seat a slab on the ground's plane under it (least squares over the grid: its slope along the street ->
            pitch, across -> roll; UE's positive roll lowers +Y), lifted so no grid point and no terrain vertex under
            it is above the slab's top (at most LIFT_MAX: past that, a junction's embankment, the ground may show).
            top: the slab's top over that plane; base: the mesh's own top (cm) after scaling."""
            g = {}
            for t in grid:
                for w in grid:
                    x, y = a[0] + ux * length * t + nx * (y0 + width * w), a[1] + uy * length * t + ny * (y0 + width * w)
                    g[t, w] = at(x, y, za + (zb - za) * t)
            mean = sum(g.values()) / len(g)
            cs = sum((t - 0.5) * z for (t, _w), z in g.items()) / var / length
            cw = sum((w - 0.5) * z for (_t, w), z in g.items()) / var / width
            c0 = mean - cs * 0.5 * length - cw * 0.5 * width
            high = [z - (c0 + cs * length * t + cw * width * w) for (t, w), z in g.items()]
            if peaks is not None:
                quad = [(a[0] + nx * y0, a[1] + ny * y0), (b[0] + nx * y0, b[1] + ny * y0),
                        (b[0] + nx * (y0 + width), b[1] + ny * (y0 + width)), (a[0] + nx * (y0 + width), a[1] + ny * (y0 + width))]
                for x, y, z in peaks(min(q[0] for q in quad), min(q[1] for q in quad), max(q[0] for q in quad),
                                     max(q[1] for q in quad)):
                    t = ((x - a[0]) * ux + (y - a[1]) * uy) / length
                    w = ((x - a[0]) * nx + (y - a[1]) * ny - y0) / width
                    if 0.0 <= t <= 1.0 and 0.0 <= w <= 1.0:
                        high.append(z - (c0 + cs * length * t + cw * width * w))
            lift = min(LIFT_MAX, max(0.0, max(high)))
            rows.append(((a[0] + nx * y0, a[1] + ny * y0, c0 + lift + top - base),
                         (math.degrees(math.atan(cs)), yaw, -math.degrees(math.atan(cw))), (sx, width / K.SLAB, sz), mesh))
        slab(K.PAVER, -hw, 2.0 * hw, SETTS_TOP, 20.0 * SETTS_Z, SETTS_Z)
        if walks[i] or walks[i + 1]:
            for y0 in (hw, -hw - settle.SIDEWALK):
                slab(K.SIDEWALK, y0, settle.SIDEWALK, SETTS_TOP + 13.0, 20.0 * WALK_Z, WALK_Z)
    return rows


def door_rise(b, ground):
    """How far building b's floor stands over the ground in front of its door, for its entrance steps: DOOR_PROBE out
    from its front's middle (the front grammar centres the door). ground(x, y) -> height or None (0 then)."""
    e = building.edges(building.ring_cw(b["x"], b["y"], b["w"], b["d"], b["yaw"]))[b["front"]]
    g = ground(e["P"][0] + e["u"][0] * 0.5 * e["L"] + e["n"][0] * DOOR_PROBE,
               e["P"][1] + e["u"][1] * 0.5 * e["L"] + e["n"][1] * DOOR_PROBE)
    return 0.0 if g is None else b["z"] - g


def drop_hanging(plans, ground):
    """Leave out the outbuildings whose ground a neighbour's 台地切挖 took away (one stood 3.3 m over its ground on the
    real valley, its door 4 m up): the leftover lot stays a yard, as City Sample leaves a lot it cannot fill. Houses,
    shops and farms stay (their plinths reach 4.45 m down). ground(x, y) -> height or None. Returns how many."""
    n = 0
    for plan in plans:
        kept = []
        for b in plan["buildings"]:
            hs = [h for h in (ground(x, y) for x, y in list(b["ring"]) + [(b["x"], b["y"])]) if h is not None]
            if b["kind"] == "Outbuilding" and hs and b["z"] - sum(hs) / len(hs) > OUTBUILDING_HANG:
                n += 1
                continue
            kept.append(b)
        plan["buildings"] = kept
    return n


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
    plans, parts, street_tables, corridors, paving = [], [], [], [], []
    for r in locs:
        cx, cy, rad = r["loc"][0], r["loc"][1], r["Radius"]
        plan = settle.layout({"id": r["Id"], "kind": r["Kind"], "x": cx, "y": cy, "radius": rad}, ctx.rng, site)
        plans.append(plan)
        if lat.n:
            a, b, c = T.fit_plane(lat, cx, cy, rad, params["MaxPlatformSlope"])
            # the plane keeps its fitted slope but passes through the ground at the centre: on a valley side the
            # least-squares plane of a concave slope stands metres above it (6 m at the town, measured 2026-10-27), and
            # the plaza -- on the road through the place, at its natural height -- sank into a bank of fill
            c = _h(lat, cx, cy, c)
            T.platform(lat, cx, cy, rad, (a, b, c), keep)
        for st in plan["streets"]:
            zs = geom.moving_average([_h(lat, x, y) for x, y in st], 3)
            pts3 = [(x, y, z) for (x, y), z in zip(st, zs)]
            walks = [rules.SIDEWALKS[rules.zone_of(math.hypot(x - cx, y - cy) / rad)] for x, y, _z in pts3]
            paved = [2.0 * (settle.STREET_HW + (settle.SIDEWALK if w else 0.0)) for w in walks]
            corridor = [(x, y, z, 0.5 * pv, False) for (x, y, z), pv in zip(pts3, paved)]
            corridors.append(corridor)
            if lat.n:
                T.flatten_corridor(lat, corridor, 100.0, 400.0)
            paving.append((pts3, walks))
            cum = geom.cumulative(st)
            street_tables.append(([{"loc": p, "Width": 2.0 * settle.STREET_HW, "Paved": pv, "S": s}
                                   for p, pv, s in zip(pts3, paved, cum)]))
        if plan["plaza"]:
            zc = _h(lat, cx, cy)
            if lat.n:
                T.pad(lat, geom.circle(cx, cy, settle.PLAZA_R, 32), zc, 200.0, 600.0)
            plan["plaza_z"] = zc
            n = int(settle.PLAZA_R // K.SLAB) + 1                              # stone slabs, pivot on a corner
            for gy in range(-n, n):
                for gx in range(-n, n):
                    if math.hypot(K.SLAB * (gx + 0.5), K.SLAB * (gy + 0.5)) <= settle.PLAZA_R - 0.5 * K.SLAB:
                        parts.append(((cx + K.SLAB * gx, cy + K.SLAB * gy, zc + PLAZA_TOP - 200.0), (0.0, 0.0, 0.0),
                                      (1.0, 1.0, 10.0), K.PLAZA_STONE))
        for b in plan["buildings"]:
            zs = [z for z in (lat.height(x, y) if lat.n else None for x, y in b["ring"] + [(b["x"], b["y"])])
                  if z is not None]
            b["z"] = sum(zs) / len(zs) if zs else 0.0
            if b.get("front_kind") in ("street", "plaza") and lat.n:
                # the door towards the street's (plaza's) level, within STREET_PULL of the ground it stands on: a
                # neighbour on another street 2 m away cannot hold a much different pad on the 5.86 m vertex grid
                dz = _h(lat, b["street"][0], b["street"][1], b["z"]) - b["z"]
                b["z"] += max(-STREET_PULL, min(STREET_PULL, dz))
            if lat.n:
                T.pad(lat, b["ring"], b["z"], 200.0, 400.0)
    if lat.n:
        for rd in sorted(roads, key=lambda r: r["cls"] != "Secondary"):
            T.flatten_corridor(lat, [(p[0], p[1], p[2], 0.5 * rd["width"], br) for p, br in zip(rd["pts"], rd["bridge"])])
        # Lock every footprint (+1 m) at its pad height last: a neighbour's pad blend or a street would otherwise tilt it.
        for plan in plans:
            for b in plan["buildings"]:
                T.pad(lat, b["ring"], b["z"], 100.0, 0.0)
        # Restore the paved streets (carriageway + sidewalks) and the plazas exactly: the pads' blends reach 6 m and
        # lifted the ground over the setts.
        for corridor in corridors:
            T.flatten_corridor(lat, corridor, 0.0, 1.0)
        for plan in plans:
            if plan["plaza"]:
                T.pad(lat, geom.circle(plan["x"], plan["y"], settle.PLAZA_R, 32), plan["plaza_z"], 0.0, 0.0)
        # Then cut the ground above each floor down to it within a vertex cell's diagonal (台地切挖): the ground at a
        # wall is interpolated from vertices up to 8.3 m away, and none of them may stand higher than the floor
        # (streets, roads and plazas keep their surface; lower ground is the plinth's to hide).
        plazas = [(p["x"], p["y"]) for p in plans if p["plaza"]]

        def keep(x, y):
            hit = site.road_lines.nearest(x, y, 3000.0)
            if hit is not None and hit[0] < site.road_lines.payload(hit[1]) + ROAD_INNER:
                return False                                  # a road's flat corridor
            if site.near_line(x, y, settle.SIDEWALK + STREET_KEEP):
                return False                                  # a street's surface and its sidewalks
            return all(math.hypot(x - px, y - py) > settle.PLAZA_R + 100.0 for px, py in plazas)
        for plan in plans:
            for b in plan["buildings"]:
                T.cut(lat, b["ring"], b["z"], CUT_REACH, keep)
    dropped = drop_hanging(plans, lambda x, y: lat.height(x, y)) if lat.n else 0
    # the streets' slabs last, on the final ground (the engine's own triangulated surface: the bilinear height is up to
    # ~16 cm off it on a twisted cell, and the ground showed through the setts across a steep street)
    def on_road(x, y):
        hit = site.road_lines.nearest(x, y, 3000.0)
        return hit is not None and hit[0] < site.road_lines.payload(hit[1]) + ROAD_INNER     # its flat corridor
    for pts3, walks in paving:
        parts += street_modules(pts3, walks, lat.tri_height if lat.n else None, on_road,
                                lat.vertices_in if lat.n else None)
    rows, areas, check, modules = [], [], geom.RingIndex(), []
    per, overlaps, on_road = {}, 0, 0
    tally = {"doors_front": 0, "awnings": 0, "balconies": 0, "chimneys": 0, "dormers": 0, "lamps": 0, "shops": 0,
             "steps": 0, "door_rise_max": 0.0, "bay_scale_min": 9.0, "bay_scale_max": 0.0, "slack_max": 0.0}
    styles, floors_by_zone = set(), {}
    for plan in plans:
        per[plan["id"]] = {"kind": plan["kind"], "n": len(plan["buildings"]),
                           "churches": sum(b["kind"] == "Church" for b in plan["buildings"])}
        for b in plan["buildings"]:
            if lat.n:
                b["door_rise"] = door_rise(b, lat.tri_height)          # the visible ground (traps 112)
            built = building.assemble(b)
            modules += built["instances"]
            st = built["stats"]
            tally["doors_front"] += st["door_edge"] == b["front"]
            for k in ("awnings", "balconies", "chimneys", "dormers", "lamps"):
                tally[k] += st[k]
            tally["shops"] += b["use"] == "shop"
            tally["steps"] += st["steps"] > 0
            tally["door_rise_max"] = max(tally["door_rise_max"], b.get("door_rise", 0.0))
            tally["bay_scale_min"] = min(tally["bay_scale_min"], st["scale_min"])
            tally["bay_scale_max"] = max(tally["bay_scale_max"], st["scale_max"])
            tally["slack_max"] = max(tally["slack_max"], st["slack_max"])
            styles.add(b["style"])
            floors_by_zone.setdefault(b["zone"], []).append(b["floors"])
            areas.append((Polygon(list(b["ring"]), [], b["z"]), ["Footprint"]))
            rows.append({"loc": (b["x"], b["y"], b["z"]), "Kind": b["kind"], "Style": b["style"],
                         "Settlement": b["settlement"], "W": b["w"], "D": b["d"], "Yaw": b["yaw"],
                         "Floors": b["floors"], "Height": built["ridge"] - b["z"], "Tint": b["tint"],
                         "Roof": b["roof_tint"], "Shop": b["use"] == "shop"})
            # terraces share walls: an overlap is where the insides meet (the rings shrunk by settle.TOUCH)
            inner = geom.rect(b["x"], b["y"], b["w"] - settle.TOUCH, b["d"] - settle.TOUCH, b["yaw"])
            overlaps += check.overlaps(inner)
            check.add(inner)
            # on a road, a street (any settlement's) or in the river
            on_road += any(site.near_line(x, y, 0.0) or site.near_river(x, y, 0.0)
                           for x, y in geom.probe_points(b["ring"], 400.0))
        if plan["plaza"]:
            areas.append((Polygon(geom.circle(plan["x"], plan["y"], settle.PLAZA_R, 32), [], plan["plaza_z"]), ["Plaza"]))
        for fr in plan["fields"]:
            areas.append((Polygon(list(fr), [], _h(lat, *geom.centroid(fr))), ["Field"]))
        for gr in plan["gardens"]:
            areas.append((Polygon(list(gr), [], _h(lat, *geom.centroid(gr))), ["Field", "Garden"]))
    # the door at street level: the final ground at the street point each street house faces, against its floor
    street_level = [abs(_h(lat, b["street"][0], b["street"][1], b["z"]) - b["z"]) for plan in plans
                    for b in plan["buildings"] if b.get("front_kind") == "street" and lat.n]
    full = geom.RingIndex()                           # terraces: a building whose wall meets a neighbour's
    for plan in plans:
        for b in plan["buildings"]:
            full.add(b["ring"])
    attached = sum(full.touching(i, 2.0 * settle.TOUCH) for i in range(len(full.rings)))

    def least(kind, key="n"):
        vals = [p[key] for p in per.values() if p["kind"] in kind]
        return min(vals) if vals else -1

    def mean(zone):
        vals = floors_by_zone.get(zone, [])
        return sum(vals) / len(vals) if vals else 0.0
    summary = {"buildings": len(rows), "town_min": least(("Town",)), "village_min": least(("Village",)),
               "hamlet_min": least(("Hamlet",)), "churches_min": least(("Town", "Village"), "churches"),
               "overlaps": int(overlaps), "on_road": int(on_road), "streets": len(street_tables),
               "plazas": sum(1 for p in plans if p["plaza"]), "fields": sum(len(p["fields"]) for p in plans),
               "gardens": sum(len(p["gardens"]) for p in plans), "outbuildings_dropped": dropped,
               "street_fronts": len(street_level), "street_level_err_max": max(street_level, default=0.0),
               "street_level_err_mean": sum(street_level) / len(street_level) if street_level else 0.0,
               "modules": len(modules), "styles": len(styles), "attached": int(attached),
               "floors_core_mean": mean("core"), "floors_outskirts_mean": mean("outskirts")}
    summary.update({k: (int(v) if isinstance(v, int) else float(v)) for k, v in tally.items()})
    ctx.notes.append("%d settlements, %d buildings, %d modules" % (len(plans), len(rows), len(modules)))
    return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets],
            "Modules": [(WP.module_points(modules), ["BuildingModule"])] if modules else [],
            "Parts": [(WP.mesh_points(parts), ["SettlementPart"])] if parts else [],
            "Buildings": [(WP.table_points(rows, TYPES), ["Building"])] if rows else [],
            "Streets": [(WP.table_points(t, {"Width": "Double", "Paved": "Double", "S": "Double"}), ["Street"])
                        for t in street_tables],
            "Areas": areas, "Summary": [(WP.summary(summary), ["Summary"])]}

