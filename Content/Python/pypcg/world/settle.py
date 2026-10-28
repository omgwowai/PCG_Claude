"""Settlement layout (视频步骤 6): the plaza, organic streets, zones, plots and fields of one location, and each
building's dressing (style, storeys, colours, the edge on the street: rules.dress). Pure and 2D; the terrain work
(platform, pads) and the module assembly (building.assemble) are W6's."""
import math
import random

from . import ROAD_BLEND, ROAD_INNER, geom, noise, rules

PLAZA_R = 1800.0
STREET_HW = 200.0
SIDEWALK = 230.0       # a raised sidewalk from the carriageway's edge to 20 cm short of the facades (rules.SIDEWALKS)
STREET_STEP = 500.0
# kind -> (lanes from the plaza, spacing of the lanes off a road through the place, total street length, longest lane,
#          branching depth): the organic growth of `layout` (cm)
GROWTH = {"Town": (3, 8000.0, 190000.0, 26000.0, 2), "Village": (2, 11000.0, 75000.0, 17000.0, 1),
          "Hamlet": (0, 6000.0, 20000.0, 9000.0, 0)}
GROW_STEP = 1000.0                   # a lane grows 10 m at a time ...
TURN_SD, TURN_MAX = math.radians(4.0), math.radians(8.0)     # ... its heading drifting (damped random walk)
SNAP = 1500.0                        # a lane within 15 m of another street or road ends on it
BRANCH_P = 0.15                      # chance per step of a side lane
ORIGIN_CLEAR = 2500.0                # a lane never ends on what it started from: its snap point is this far from its start
SETBACK = {"street": 250.0, "road": ROAD_INNER + ROAD_BLEND + 50.0}   # beyond the road corridor W6 restores last
TOUCH = 10.0           # a terrace's lots are tested shrunk by this, so neighbours may share a wall
LANDMARK_CLEAR = 120.0 # free ground round a landmark (the bell tower, grown by 50, stands 200 from its church)
RETRY = {"core": 100.0, "residential": 400.0, "outskirts": 400.0}       # step along the front after a refused lot
# (bearing offset, extra distance) a landmark tries, in order
LANDMARK_TRIES = [(da, extra) for extra in (0.0, 800.0, 1600.0, 2400.0, 3200.0, 4000.0) for da in (0.0, 15.0, -15.0, 30.0, -30.0, 45.0, -45.0, 60.0, -60.0)]


def angle_gap(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def pick_bearings(n, taken, rng, min_sep=35.0):
    """Up to n directions, each as far as possible from `taken` and the ones already chosen (5 degree steps from a
    random start); stops when the best is closer than min_sep to something."""
    chosen = []
    base = rng.uniform(0.0, 360.0)
    for _ in range(n):
        best = None
        for q in range(72):
            a = (base + 5.0 * q) % 360.0
            m = min([angle_gap(a, b) for b in list(taken) + chosen], default=180.0)
            if best is None or m > best[0]:
                best = (m, a)
        if best[0] < min_sep:
            break
        chosen.append(best[1])
    return chosen


def widest_gap(bearings, rng):
    if not bearings:
        return rng.uniform(0.0, 360.0)
    b = sorted(x % 360.0 for x in bearings)
    gaps = [((b[(i + 1) % len(b)] - b[i]) % 360.0 or 360.0, b[i]) for i in range(len(b))]
    g, start = max(gaps)
    return (start + 0.5 * g) % 360.0


def runs_within(pts, cx, cy, r):
    runs, cur = [], []
    for p in pts:
        if math.hypot(p[0] - cx, p[1] - cy) <= r:
            cur.append((p[0], p[1]))
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


class Site:
    """What a plot must keep clear of: roads and streets (with their half widths), the river (with its widths) and
    every ring already placed -- `taken` is shared by all settlements."""

    def __init__(self, roads, river, taken):
        self.roads = roads
        self.lines = geom.SegmentIndex(2000.0)
        self.road_lines = geom.SegmentIndex(2000.0)          # roads only: their corridor is restored after the pads
        for rd in roads:
            self.lines.add_polyline([p[:2] for p in rd["pts"]], rd["hw"])
            self.road_lines.add_polyline([p[:2] for p in rd["pts"]], rd["hw"])
        self.river = geom.SegmentIndex(2000.0)
        for a, b in zip(river, river[1:]):
            self.river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
        self.taken = taken

    def add_street(self, pts):
        self.lines.add_polyline(pts, STREET_HW)

    def near_line(self, x, y, margin):
        hit = self.lines.nearest(x, y, 3000.0 + margin)
        return hit is not None and hit[0] < self.lines.payload(hit[1]) + margin

    def near_river(self, x, y, margin):
        hit = self.river.nearest(x, y, 3000.0 + margin)
        return hit is not None and hit[0] < 0.5 * self.river.payload(hit[1]) + margin

    def free(self, ring, grown, cx, cy, limit):
        for x, y in geom.probe_points(ring, 400.0):
            if math.hypot(x - cx, y - cy) > limit or self.near_line(x, y, 150.0) or self.near_river(x, y, 1000.0):
                return False
            hit = self.road_lines.nearest(x, y, 3000.0 + ROAD_INNER + ROAD_BLEND)
            if hit is not None and hit[0] < self.road_lines.payload(hit[1]) + ROAD_INNER + ROAD_BLEND:
                return False                   # inside a road corridor, which W6 flattens again after the pads
        return not self.taken.overlaps(grown)


def road_bearings(cx, cy, r, roads):
    out = []
    for rd in roads:
        for p in rd["pts"]:
            d = math.hypot(p[0] - cx, p[1] - cy)
            if d <= 0.8 * r:
                out.append(math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360.0)
    return out


def _clear(site, x0, y0, x1, y1, step=250.0):
    """No building within a street's half width + 1.5 m anywhere along the segment (a 10 m step can clip a corner)."""
    n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
    return not any(site.taken.near(x0 + (x1 - x0) * q / n, y0 + (y1 - y0) * q / n, STREET_HW + 150.0)
                   for q in range(1, n + 1))


def grow(site, cx, cy, limit, x, y, heading, rng, max_len):
    """One street from (x, y): GROW_STEP steps, the heading drifting as a damped random walk (a lane follows plots and
    fences, not a ruler). It stops outside `limit(bearing)`, at the river or a building, or when it comes within SNAP
    of another street or road -- it then ends on it, a T junction. Returns (points, branch points)."""
    pts, turn, length, branches = [(x, y)], 0.0, 0.0, []
    while length < max_len:
        turn = max(-TURN_MAX, min(TURN_MAX, 0.6 * turn + rng.gauss(0.0, TURN_SD)))
        heading += turn
        nx, ny = x + GROW_STEP * math.cos(heading), y + GROW_STEP * math.sin(heading)
        if math.hypot(nx - cx, ny - cy) > limit(math.atan2(ny - cy, nx - cx)):
            break
        if site.near_river(nx, ny, 800.0) or not _clear(site, x, y, nx, ny):
            break                                     # the river, or a building (a landmark, an earlier settlement)
        if len(pts) >= 3:                             # clear of where it started: it joins what it reaches
            hit = site.lines.nearest(nx, ny, SNAP)
            if hit is not None:
                (ax, ay), (bx, by) = site.lines.segment(hit[1])
                jx, jy = ax + (bx - ax) * hit[2], ay + (by - ay) * hit[2]
                if math.hypot(jx - pts[0][0], jy - pts[0][1]) > ORIGIN_CLEAR:
                    if _clear(site, x, y, jx, jy):
                        pts.append((jx, jy))
                    return pts, branches
        pts.append((nx, ny))
        x, y, length = nx, ny, length + GROW_STEP
        if len(pts) >= 4 and rng.random() < BRANCH_P:
            branches.append((x, y, heading))
    return pts, branches


def layout(loc, rng, site):
    cx, cy, r, kind, sid = loc["x"], loc["y"], loc["radius"], loc["kind"], loc["id"]
    n_plaza, spacing, budget, longest, depth_max = GROWTH[kind]
    plaza = (cx, cy, PLAZA_R) if kind != "Hamlet" else None
    taken_bearings = road_bearings(cx, cy, r, site.roads)
    buildings, fields, counts = [], [], {}

    def place(spec, bx, by, w, d, yaw, gap, special=None, front=2, zone=None, avoid_tint=None, street=None,
              front_kind=None):
        """`front` is the edge on the street or the plaza (building.py's edge numbering); `street` the point of the
        street (or plaza) it faces, whose height W6 gives its ground floor (front_kind "street" / "plaza")."""
        ring = geom.rect(bx, by, w, d, yaw)
        grow = gap if gap > 0.0 else -TOUCH
        if not site.free(ring, geom.rect(bx, by, w + grow, d + grow, yaw), cx, cy, 0.97 * r):
            return None
        # a landmark keeps LANDMARK_CLEAR round it: core terraces would otherwise lean on it and their pads tilt it
        site.taken.add(geom.rect(bx, by, w + 2.0 * LANDMARK_CLEAR, d + 2.0 * LANDMARK_CLEAR, yaw) if special else ring)
        zone = zone or rules.zone_of(math.hypot(bx - cx, by - cy) / r)
        near = plaza is not None and math.hypot(bx - cx, by - cy) < PLAZA_R + 0.5 * max(w, d) + 1500.0
        b = {"kind": spec["kind"], "ring": ring, "x": bx, "y": by, "w": w, "d": d, "yaw": yaw, "special": special,
             "settlement": sid, "zone": zone, "front": front, "street": street, "front_kind": front_kind}
        # dressing draws from its own generator, seeded by the lot: the layout's draws (streets, lots) stay as they were
        drng = random.Random((sid * 1000003 + int(round(bx)) * 7919 + int(round(by))) & 0xFFFFFFFF)
        b.update(rules.dress(spec["kind"], zone, kind, bx, by, sid, w, d, drng, near, avoid_tint))
        buildings.append(b)
        counts[spec["kind"]] = counts.get(spec["kind"], 0) + 1
        return b

    # The landmarks first, facing the plaza in the widest gaps between the roads; the streets then grow round them.
    landmark_dirs = []
    if plaza:
        for spec in [spec for spec in rules.LANDMARKS if kind in spec["settlements"]]:
            a0 = widest_gap(taken_bearings + landmark_dirs, rng)
            landmark_dirs.append(a0)
            # The widest gap first, then directions and distances around it: a river may block the gap.
            b = None
            for da, extra in LANDMARK_TRIES:
                a = (a0 + da) % 360.0
                ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
                off = PLAZA_R + 300.0 + extra + 0.5 * spec["w"]
                b = place(spec, cx + ux * off, cy + uy * off, spec["w"], spec["d"], a, 300.0, spec["kind"], front=3,
                          zone="core", street=(cx, cy), front_kind="plaza")
                if b is not None:
                    break
            if b is not None and spec.get("tower"):
                px, py = -uy, ux
                for side in (1.0, -1.0):
                    tx = cx + ux * (PLAZA_R + 300.0 + 0.5 * rules.TOWER["w"] + extra) + side * px * (0.5 * spec["d"] + 0.5 * rules.TOWER["d"] + 200.0)
                    ty = cy + uy * (PLAZA_R + 300.0 + 0.5 * rules.TOWER["w"] + extra) + side * py * (0.5 * spec["d"] + 0.5 * rules.TOWER["d"] + 200.0)
                    if place(rules.TOWER, tx, ty, rules.TOWER["w"], rules.TOWER["d"], a, 100.0, "BellTower", front=3,
                             zone="core", street=(cx, cy), front_kind="plaza") is not None:
                        break
    # Streets grow (视频：内部路网连到最近道路；有机生长而不是放射 + 环路): lanes leave the plaza and branch off the roads
    # through the place at irregular intervals; every lane wanders, may sprout side lanes, and ends on the first
    # street or road it meets. The settlement's edge is a noisy circle, so lanes stop at different distances.
    phase = rng.uniform(0.0, 100.0)

    def limit(bearing):
        return r * (0.72 + 0.22 * noise.value(1.4 * math.cos(bearing) + phase, 1.4 * math.sin(bearing) + phase, sid + 17))
    seeds = []
    if plaza:
        for a in pick_bearings(n_plaza, taken_bearings + landmark_dirs, rng, 50.0):
            a = math.radians(a + rng.uniform(-20.0, 20.0))
            seeds.append((cx + PLAZA_R * math.cos(a), cy + PLAZA_R * math.sin(a), a, 0, longest))
    for rd in site.roads:
        for run in runs_within(rd["pts"], cx, cy, 0.85 * r):
            cum = geom.cumulative(run)
            s, side = rng.uniform(0.2, 0.8) * spacing, rng.choice((1.0, -1.0))
            while spacing and s < cum[-1] - 1500.0:
                (x, y), yaw = geom.at_distance(run, cum, s)
                if math.hypot(x - cx, y - cy) > PLAZA_R + 1500.0:
                    seeds.append((x, y, math.radians(yaw + 90.0 * side + rng.uniform(-30.0, 30.0)), 0, longest))
                s += spacing * rng.uniform(0.6, 1.4)
                side = -side if rng.random() < 0.75 else side
    if not seeds:                                     # a hamlet off the road's end: lanes from its centre
        for a in pick_bearings(2, taken_bearings, rng, 70.0):
            seeds.append((cx, cy, math.radians(a), 0, longest))
    seeds.sort(key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
    streets, used, queue = [], 0.0, list(seeds)
    while queue and used < budget:
        x, y, heading, depth, most = queue.pop(0)
        pts, branches = grow(site, cx, cy, limit, x, y, heading, rng, min(most, budget - used))
        if len(pts) < 3:
            continue
        pts = geom.resample(pts, STREET_STEP)
        streets.append(pts)
        site.add_street(pts)
        used += geom.length(pts)
        if depth < depth_max:
            for bx, by, bh in branches:
                queue.append((bx, by, bh + math.radians(rng.choice((1.0, -1.0)) * rng.uniform(70.0, 110.0)),
                              depth + 1, 0.6 * most))
    fronts = [(st, STREET_HW, "street") for st in streets]
    for rd in site.roads:
        fronts += [(run, rd["hw"], "road") for run in runs_within(rd["pts"], cx, cy, r)]
    for pts, hw, what in fronts:
        cum = geom.cumulative(pts)
        total = cum[-1]
        for side in (1.0, -1.0):
            s, last_tint = 300.0, None
            while s < total - 300.0:
                (x, y), _yaw = geom.at_distance(pts, cum, s)
                zone = rules.zone_of(math.hypot(x - cx, y - cy) / r)
                spec = rules.pick(zone, kind, counts, rng)
                if spec is None:
                    s += 400.0
                    continue
                w, d = rng.uniform(*rules.frontage(spec, zone)), rng.uniform(*spec["d"])
                gap = 0.0 if rng.random() < rules.TERRACE_P[zone] else rng.uniform(*rules.GAPS[zone])
                (mx, my), yaw = geom.at_distance(pts, cum, min(total, s + 0.5 * w))
                nx, ny = -math.sin(math.radians(yaw)) * side, math.cos(math.radians(yaw)) * side
                # the street is behind the lot's -d side when it stands on the left (+n), behind +d on the right;
                # a terrace lot on the inside of a bend is made shallower before it gives up (its back would overlap)
                for depth in ((d, 0.85 * d, 0.7 * d) if gap == 0.0 else (d,)):
                    off = hw + SETBACK[what] + 0.5 * depth
                    b = place(spec, mx + nx * off, my + ny * off, w, depth, yaw, gap, front=2 if side > 0 else 0,
                              zone=zone, avoid_tint=last_tint, street=(mx, my), front_kind=what)
                    if b is not None:
                        d = depth
                        break
                if b is None:
                    s += RETRY[zone]
                    continue
                last_tint = b["tint"]
                if spec.get("field"):
                    fw, fd = rng.uniform(2500.0, 4000.0), rng.uniform(3000.0, 5000.0)
                    o2 = off + 0.5 * d + 400.0 + 0.5 * fd
                    fr = geom.rect(mx + nx * o2, my + ny * o2, fw, fd, yaw)
                    if site.free(fr, fr, cx, cy, 1.3 * r):
                        site.taken.add(fr)
                        fields.append(fr)
                s += w + gap
    # Leftover lots (City Sample stage 13): behind a street house, by its zone's odds, an outbuilding facing the
    # house and a kitchen garden beyond it -- where the ground behind is free.
    gardens = []
    for b in [b for b in buildings if b["kind"] in ("House", "Shop") and b["front"] in (0, 2)]:
        p_out, p_garden = rules.BACKYARD[b["zone"]]
        back = 1.0 if b["front"] == 2 else -1.0                    # the street side's opposite, along the lot's +d
        ux, uy = -math.sin(math.radians(b["yaw"])) * back, math.cos(math.radians(b["yaw"])) * back
        reach = 0.5 * b["d"]
        if rng.random() < p_out:
            ow, od = rng.uniform(*rules.OUTBUILDING["w"]), rng.uniform(*rules.OUTBUILDING["d"])
            c = reach + rng.uniform(150.0, 400.0) + 0.5 * od
            ob = place(rules.OUTBUILDING, b["x"] + ux * c, b["y"] + uy * c, min(ow, b["w"]), od, b["yaw"], 100.0,
                       front=b["front"], zone=b["zone"])
            if ob is not None:
                reach = c + 0.5 * od
        if rng.random() < p_garden:
            gw, gd = b["w"] * rng.uniform(0.7, 1.0), rng.uniform(600.0, 1200.0)
            c = reach + 200.0 + 0.5 * gd
            gr = geom.rect(b["x"] + ux * c, b["y"] + uy * c, gw, gd, b["yaw"])
            if site.free(gr, gr, cx, cy, 1.05 * r):
                site.taken.add(gr)
                gardens.append(gr)
    return {"id": sid, "kind": kind, "x": cx, "y": cy, "r": r, "plaza": plaza, "streets": streets,
            "buildings": buildings, "fields": fields, "gardens": gardens}
