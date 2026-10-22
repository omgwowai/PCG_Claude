"""Settlement layout (视频步骤 6): the plaza, radial and ring streets, zones, plots and fields of one location.
Pure and 2D; the terrain work (platform, pads) is W6's."""
import math

from . import geom, rules

PLAZA_R = 1800.0
STREET_HW = 200.0
STREET_STEP = 500.0
SETBACK = {"street": 250.0, "road": 700.0}       # a road's flat corridor reaches half width + 600 (ROAD_INNER)
GAP = (300.0, 600.0)


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
        for rd in roads:
            self.lines.add_polyline([p[:2] for p in rd["pts"]], rd["hw"])
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
        return not self.taken.overlaps(grown)


def road_bearings(cx, cy, r, roads):
    out = []
    for rd in roads:
        for p in rd["pts"]:
            d = math.hypot(p[0] - cx, p[1] - cy)
            if d <= 0.8 * r:
                out.append(math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360.0)
    return out


def layout(loc, rng, site):
    cx, cy, r, kind, sid = loc["x"], loc["y"], loc["radius"], loc["kind"], loc["id"]
    n_streets, ring_street = rules.STREETS[kind]
    plaza = (cx, cy, PLAZA_R) if kind != "Hamlet" else None
    start = PLAZA_R if plaza else 600.0
    taken_bearings = road_bearings(cx, cy, r, site.roads)
    # The landmarks take the widest gaps between the roads first; the streets then keep out of their way.
    landmark_dirs = []
    if plaza:
        for spec in rules.LANDMARKS:
            if kind in spec["settlements"]:
                landmark_dirs.append(widest_gap(taken_bearings + landmark_dirs, rng))
    bearings = pick_bearings(n_streets, taken_bearings + landmark_dirs, rng)
    streets = []
    for a in bearings:
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        pts, d = [], start
        while d <= 0.9 * r:
            x, y = cx + ux * d, cy + uy * d
            if site.near_river(x, y, 800.0):
                break
            pts.append((x, y))
            d += STREET_STEP
        if len(pts) >= 2:
            streets.append(pts)
    if ring_street:
        run = []
        for q in range(49):
            x = cx + 0.55 * r * math.cos(2.0 * math.pi * q / 48)
            y = cy + 0.55 * r * math.sin(2.0 * math.pi * q / 48)
            if site.near_river(x, y, 800.0):
                if len(run) >= 2:
                    streets.append(run)
                run = []
            else:
                run.append((x, y))
        if len(run) >= 2:
            streets.append(run)
    for st in streets:
        site.add_street(st)
    buildings, fields, counts = [], [], {}

    def place(spec, bx, by, w, d, yaw, gap, special=None):
        ring = geom.rect(bx, by, w, d, yaw)
        if not site.free(ring, geom.rect(bx, by, w + gap, d + gap, yaw), cx, cy, 0.97 * r):
            return None
        site.taken.add(ring)
        b = {"kind": spec["kind"], "group": rng.choice(spec["height"]), "ring": ring, "x": bx, "y": by, "w": w, "d": d,
             "yaw": yaw, "special": special, "settlement": sid}
        buildings.append(b)
        counts[spec["kind"]] = counts.get(spec["kind"], 0) + 1
        return b

    if plaza:
        specs = [spec for spec in rules.LANDMARKS if kind in spec["settlements"]]
        for spec, a in zip(specs, landmark_dirs):
            ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
            off = PLAZA_R + 300.0 + 0.5 * spec["w"]
            b = place(spec, cx + ux * off, cy + uy * off, spec["w"], spec["d"], a, 300.0, spec["kind"])
            if b is not None and spec.get("tower"):
                px, py = -uy, ux
                tx = cx + ux * (PLAZA_R + 600.0) + px * (0.5 * spec["d"] + 350.0)
                ty = cy + uy * (PLAZA_R + 600.0) + py * (0.5 * spec["d"] + 350.0)
                place(rules.TOWER, tx, ty, 600.0, 600.0, a, 100.0, "BellTower")
    fronts = [(st, STREET_HW, "street") for st in streets]
    for rd in site.roads:
        fronts += [(run, rd["hw"], "road") for run in runs_within(rd["pts"], cx, cy, r)]
    for pts, hw, what in fronts:
        cum = geom.cumulative(pts)
        total = cum[-1]
        for side in (1.0, -1.0):
            s = 300.0
            while s < total - 300.0:
                (x, y), _yaw = geom.at_distance(pts, cum, s)
                spec = rules.pick(rules.zone_of(math.hypot(x - cx, y - cy) / r), kind, counts, rng)
                if spec is None:
                    s += 400.0
                    continue
                w, d, gap = rng.uniform(*spec["w"]), rng.uniform(*spec["d"]), rng.uniform(*GAP)
                (mx, my), yaw = geom.at_distance(pts, cum, min(total, s + 0.5 * w))
                nx, ny = -math.sin(math.radians(yaw)) * side, math.cos(math.radians(yaw)) * side
                off = hw + SETBACK[what] + 0.5 * d
                b = place(spec, mx + nx * off, my + ny * off, w, d, yaw, gap)
                if b is None:
                    s += 400.0
                    continue
                if spec.get("field"):
                    fw, fd = rng.uniform(2500.0, 4000.0), rng.uniform(3000.0, 5000.0)
                    o2 = off + 0.5 * d + 400.0 + 0.5 * fd
                    fr = geom.rect(mx + nx * o2, my + ny * o2, fw, fd, yaw)
                    if site.free(fr, fr, cx, cy, 1.3 * r):
                        site.taken.add(fr)
                        fields.append(fr)
                s += w + gap
    return {"id": sid, "kind": kind, "x": cx, "y": cy, "r": r, "plaza": plaza, "streets": streets,
            "buildings": buildings, "fields": fields}
