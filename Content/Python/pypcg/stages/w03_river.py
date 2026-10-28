"""PyWorld W3 -- the river (视频步骤 4：河流与道路同一套寻路模型，只是容差不同；河曲形状按天然河道).

Course. A* (16 directions) from the source to the outlet on every second terrain vertex (11.7 m) along the lowest
ground, keeping out of the inner half of every location; on a flat floor a low-frequency drift cost (Wander, 450 m)
lets the course wander across it as real meander belts do. Smoothed into a gentle base line (Gaussian, 60 m). The channel
is then walked along the base line in 4 m steps: its heading is the base line's direction plus the Kinoshita meander
angle theta = A sin(phi) + A^3 (Js cos(3 phi) - Jf sin(3 phi)) (sine-generated bends skewed downstream, the standard
model of natural meanders), minus a pull back towards the base line; the phase advances with the channel's own length
over a wavelength of MeanderWavelength x the width (10-14 widths in nature), at least 180 m. Each bend draws its own wavelength
(0.5-1.9 x) and angle (0.5-1.3 x), and the angle eases off on steep reaches, near towns and at both ends. The
walker's heading turns at most 4 m / R per step (R: 2.2 widths, at least 25 m), so no bend is tighter than that. The heading changes smoothly,
so the river has no straight stretch and no kink.

Width: WidthStart..WidthEnd along the river, +-20 % noise, up to 25 % wider in the bends (pools and riffles). Water line: the running minimum of the
ground along the channel, 80 cm under, smoothed and never rising. Cross sections (terraform.carve_channel): a pool at
the outer bank of every bend with a steep cut bank, a gravel point bar on the inner bank, shallower riffles between.
The water surface is one continuous mesh (geo.Mesh -> Spawn Dynamic Mesh) with a cross section every 5 m, a little
wider than the water so that its edge tucks under the banks (the shoreline is where the water meets the ground); UV in
metres, vertex colour R = 1 on the centre line .. 0 at the edges, G = flow speed (M_PyWorldStream)."""
import math

from pypcg.geo import Mesh, Points
from pypcg.stage_api import Param
from pypcg.world import VERTEX_CM, astar, geom, hydro, noise, points as WP, shape, terraform as T
from pypcg.world.grid import Lattice
from pypcg.world.terraform import smoothstep

STAGE = 103
RECORD = "w03"
DOC = """PyWorld W3 River (河流): A* from the source to the outlet along low ground, then walked into sine-generated
(Kinoshita) meanders; the width varies, the water line falls monotonically; pools, cut banks and point bars are carved
into the terrain and one continuous water surface is laid over the channel."""
RANDOM = True
PARAMS = {
    "WidthStart": Param(600.0, "River width at the source (cm)", type="Double"),
    "WidthEnd": Param(2000.0, "River width at the outlet (cm)", type="Double"),
    "Depth": Param(150.0, "Bed depth scale (cm): riffles 0.8 x, the pools of tight bends 1.4 x", type="Double"),
    "MeanderAngle": Param(65.0, "Largest angle between the channel and the valley in a bend (degrees): 0 straight, "
                                "110 loops", type="Double"),
    "MeanderWavelength": Param(12.0, "Length of one meander (two bends) in channel widths, before each bend draws "
                                     "0.5-1.9 x (mean 14: 10-14 in nature)", type="Double"),
    "TownAvoid": Param(20.0, "Extra cost per cm inside the inner half of a location", type="Double"),
    "Wander": Param(0.8, "Large-scale drift of the course across a flat floor: 0 = the lowest line, 1 = strong",
                    type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "River", "Water", "Summary")
GRID_HALF = 140000.0
WANDER_CM = 45000.0              # the scale of the course's drift across the floor
LOW_CELLS, LOW_CM = 13, 80.0     # local floor: lowest ground within 13 coarse cells; 80 cm above it doubles the cost
BASE_SIGMA = 6000.0              # the base line's smoothing (cm)
LAMBDA_MIN = 18000.0             # no meander shorter than this: a creek's bends stay wider than the terrain's 5.9 m cells
MIN_RADIUS_W, MIN_RADIUS_CM = 2.2, 2500.0      # no bend tighter than 2.2 base widths (1.5 local widths) or 25 m
WALK = 400.0                     # the channel is walked in 4 m steps ...
ROW_CM = 500.0                   # ... and published every 5 m
WATER_UNDER = 80.0
JS, JF = 1.0 / 32.0, 1.0 / 192.0     # Kinoshita skewness and flatness
TOWN_CLEAR = 300.0               # the channel stays this far outside the inner half of a location
CROSS = 7                        # vertices across the water surface
TUCK = 150.0                     # the surface reaches this far past the water's edge, under the banks
SURFACE_LIFT = 3.0
WATER_MATERIAL = "/Game/PyPCG/World/M_PyWorldStream.M_PyWorldStream"
TYPES = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double", "Curv": "Double", "BarW": "Double"}


def river_rows(items):
    """[(x, y, water, width, bed, s, curv, bar)] of every `River` point table, ordered by S. curv: signed curvature
    (1/cm), > 0 when the bend's centre lies to the left of the flow; bar: the point bar's width on the inner bank (cm)."""
    rows = []
    for v, tags in items:
        if isinstance(v, Points) and "River" in tags:
            for r in WP.rows_of(v):
                rows.append((r["loc"][0], r["loc"][1], r["WaterZ"], r["Width"], r["BedZ"], r["S"],
                             r.get("Curv") or 0.0, r.get("BarW") or 0.0))
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
            "water_drop_cm": 0.0, "sinuosity": 1.0, "straight_share": 0.0, "max_turn_deg": 0.0, "min_radius_m": 0.0,
            "bends": 0, "width_cv": 0.0}
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def push_out(pts, towns, clear):
    """Every point moved radially out of the circles (x, y, r + clear) it falls in."""
    out = []
    for x, y in pts:
        for tx, ty, tr in towns:
            d = math.hypot(x - tx, y - ty)
            if d < tr + clear:
                if d < 1e-6:
                    x, y = tx + tr + clear, ty
                else:
                    x, y = tx + (x - tx) * (tr + clear) / d, ty + (y - ty) * (tr + clear) / d
        out.append((x, y))
    return out


class Base:
    """The base line as a walkable path: projection of a point to (arc length, direction, signed offset)."""

    def __init__(self, pts):
        self.pts = pts
        self.cum = geom.cumulative(pts)
        self.total = self.cum[-1]
        self.i = 0

    def project(self, x, y):
        """(s, heading rad, e): arc length of the nearest point, the line's direction there, the signed distance
        (+ to the left). Searches forward from the last answer: the walker moves on."""
        pts, best = self.pts, None
        for j in range(max(0, self.i - 5), min(len(pts) - 1, self.i + 40)):
            d, t = geom.seg_point(x, y, pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1])
            if best is None or d < best[0]:
                best = (d, j, t)
        d, j, t = best
        self.i = j
        a, b = pts[j], pts[j + 1]
        left = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]) > 0.0
        return (self.cum[j] + t * (self.cum[j + 1] - self.cum[j]), math.atan2(b[1] - a[1], b[0] - a[0]),
                d if left else -d)


def walk(base, width_of, angle, wavelength, seed, damp):
    """The channel: from the base line's start, heading = base direction + Kinoshita angle - pull to the base line,
    until the base line's end. width_of(s) and damp(s) take the base line's arc length."""
    b = Base(base)
    x, y = base[0]
    pts, phi, lam, heading = [(x, y, 0.0)], 0.0, LAMBDA_MIN, None
    for _ in range(int(8 * b.total / WALK) + 200):
        sb, beta, e = b.project(x, y)
        if b.total - sb <= WALK:
            break
        # bends so far: a bend's apex (the channel parallel to the valley, theta = 0) is at phi = n pi. Each bend draws its
        # own wavelength, constant from inflection to inflection (k = n + 1/2, where the curvature is 0, so the switch
        # leaves no mark), and its own angle, read at the apex and eased between bends (a jump would kink the heading)
        k = 2.0 * phi / (2.0 * math.pi)
        w = width_of(sb)
        lam = max(wavelength * w, LAMBDA_MIN) * (0.5 + 1.4 * noise.value(math.floor(k + 0.5), 0.0, seed + 31))
        taper = min(1.0, sb / (0.5 * lam), (b.total - sb) / (0.5 * lam))
        a = angle * (0.5 + 0.8 * noise.value(k, 0.0, seed + 37)) * taper * damp(sb)
        theta = a * math.sin(phi) + a ** 3 * (JS * math.cos(3.0 * phi) - JF * math.sin(3.0 * phi))
        # the pull back to the base line tightens over the last wavelength, so the river ends on it at the outlet
        pull = 0.8 * lam * min(1.0, max(0.15, (b.total - sb) / lam))
        want = beta + theta - math.atan(e / pull)
        # steering limit: no bend tighter than MIN_RADIUS_W widths or MIN_RADIUS_CM, whatever the terms add up to
        turn = WALK / max(MIN_RADIUS_W * w, MIN_RADIUS_CM)
        heading = want if heading is None else heading + max(-turn, min(turn, (want - heading + math.pi) % (2.0 * math.pi) - math.pi))
        x, y = x + WALK * math.cos(heading), y + WALK * math.sin(heading)
        pts.append((x, y, sb))
        phi += 2.0 * math.pi * WALK / lam
    return [(x, y) for x, y, _sb in pts]


def flow_speed(water, step):
    """0..1 per row from the water line's slope (1 at 1 %)."""
    n, out = len(water), []
    for i in range(n):
        a, b = water[max(0, i - 2)], water[min(n - 1, i + 2)]
        span = (min(n - 1, i + 2) - max(0, i - 2)) * step
        out.append(smoothstep(0.0, 0.01, (a - b) / span if span else 0.0))
    return out


def surface(pts, water, width, cum, speed):
    """The water surface: CROSS vertices across every row (from the right bank to the left), TUCK past the water's
    edge, at the water line; triangles wound the way the engine draws from above (geo.Mesh)."""
    n = CROSS
    verts, nrm, uvs, cols, tris = [], [], [], [], []
    for i, (x, y) in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        nx, ny = -(b[1] - a[1]) / ln, (b[0] - a[0]) / ln
        half = 0.5 * width[i] + TUCK
        for j in range(n):
            t = 2.0 * j / (n - 1) - 1.0
            verts.append((x + nx * t * half, y + ny * t * half, water[i] + SURFACE_LIFT))
            nrm.append((0.0, 0.0, 1.0))
            uvs.append((cum[i] / 100.0, (t + 1.0) * half / 100.0))
            cols.append((max(0.0, 1.0 - abs(t) * half / (0.5 * width[i])), speed[i], 0.0, 1.0))
    for i in range(len(pts) - 1):
        for j in range(n - 1):
            a = i * n + j
            tris += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    return Mesh(verts, tris, nrm, uvs, cols, WATER_MATERIAL)


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    up = inputs.get("Upstream", [])
    ends = [r for v in WP.values_tagged(inputs, "Upstream", "RiverEnd") for r in WP.rows_of(v)]
    towns = [(r["loc"][0], r["loc"][1], 0.5 * r["Radius"]) for v in WP.values_tagged(inputs, "Upstream", "Location")
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
    seed, avoid, wander = ctx.seed, params["TownAvoid"], params["Wander"]
    # Low ground first: the height above the local floor (the lowest ground within ~150 m) costs quadratically, so the
    # course keeps to the valley's low line and its water is never perched above lower ground beside it. On a flat
    # floor a low-frequency drift factor decides instead, and the course wanders as real meander belts do.
    low = hydro.min_filter(co, LOW_CELLS)
    drift = [None if z is None else math.exp(1.5 * wander * noise.fbm(co.xy(k)[0] / WANDER_CM, co.xy(k)[1] / WANDER_CM,
                                                                      seed + 13, 2)) for k, z in enumerate(co.z)]

    def cost(a, b, length):
        za, zb = co.z[a], co.z[b]
        x, y = co.xy(b)
        c = length * drift[b] * (1.0 + ((zb - low[b]) / LOW_CM) ** 2 + (zb - zmin) / 4000.0) + 60.0 * max(0.0, zb - za)
        for tx, ty, tr in towns:
            if math.hypot(x - tx, y - ty) < tr:
                c += length * avoid
        return c
    # the heuristic must not exceed the cheapest cost per cm (the lowest drift), or A* runs straight at the outlet
    path = None
    if ka is not None and kb is not None:
        path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES16, h_scale=math.exp(-1.5 * wander))
    if not path or len(path) < 2:
        ctx.notes.append("no river path")
        return {"Terrain": terrain_out(), "River": [], "Water": [], "Summary": _summary()}
    base = geom.smooth_polyline([co.xy(k) for k in path], BASE_SIGMA, 1000.0)
    base = geom.smooth_polyline(push_out(base, towns, TOWN_CLEAR + 1500.0), 2000.0, 1000.0)
    bcum = geom.cumulative(base)
    btotal = bcum[-1]
    ws, we, depth = params["WidthStart"], params["WidthEnd"], params["Depth"]
    width_of = lambda s: ws + (we - ws) * min(1.0, max(0.0, s / btotal if btotal else 0.0))
    # the valley's fall along the base line: steep reaches meander less
    bground = geom.gaussian([lat.height(x, y) or 0.0 for x, y in base], 10.0)
    bslope = [abs(bground[min(i + 1, len(base) - 1)] - bground[max(i - 1, 0)])
              / max(1.0, bcum[min(i + 1, len(base) - 1)] - bcum[max(i - 1, 0)]) for i in range(len(base))]

    def damp(s):
        i = min(len(base) - 1, max(0, int(round(s / max(btotal, 1.0) * (len(base) - 1)))))
        x, y = base[i]
        near = min((math.hypot(x - tx, y - ty) - tr for tx, ty, tr in towns), default=1e9)
        return (1.0 - 0.5 * smoothstep(0.02, 0.06, bslope[i])) * smoothstep(TOWN_CLEAR, TOWN_CLEAR + 9000.0, near)
    angle, chan = math.radians(params["MeanderAngle"]), None
    for _try in range(4):
        raw = push_out(walk(base, width_of, angle, params["MeanderWavelength"], seed, damp), towns, TOWN_CLEAR)
        chan = geom.resample(geom.smooth_polyline(raw, 600.0, ROW_CM), ROW_CM)
        if not geom.self_intersects(chan):
            break
        angle *= 0.8                                  # a bend closed on its neighbour: calmer meanders
    cum = geom.cumulative(chan)
    total = cum[-1]
    onto = Base(base)                                 # each row's width from its place along the base line, as the walk
    w0 = [width_of(onto.project(x, y)[0]) for x, y in chan]
    w0[0], w0[-1] = ws, we
    curv = geom.gaussian(shape.curvature(chan), 2.0)
    bend = [max(-1.0, min(1.0, k * 2.5 * w)) for k, w in zip(curv, w0)]
    width, bar = [], []
    for s, w, c in zip(cum, w0, bend):
        ends_in = min(1.0, s / 2000.0, (total - s) / 2000.0)        # exact widths at the source and the outlet
        n = noise.fbm(s / (5.0 * w), 0.53, seed + 41, 2)
        width.append(w * (1.0 + ends_in * (0.2 * n + 0.25 * abs(c))))
        bar.append(0.35 * w * abs(c) * ends_in)
    ground, last = [], None
    for x, y in chan:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    water = []
    for g in ground:
        water.append(min(water[-1], g - WATER_UNDER) if water else g - WATER_UNDER)
    water = geom.moving_average(water, 12)
    for i in range(1, len(water)):
        water[i] = min(water[i], water[i - 1])
    carved = T.carve_channel(lat, [(p[0], p[1], w, wd, c, br) for p, w, wd, c, br in zip(chan, water, width, bend, bar)],
                             depth)
    beds = [w - depth * (0.8 + 0.6 * abs(c)) for w, c in zip(water, bend)]
    rows = [{"loc": (p[0], p[1], w), "Width": wd, "WaterZ": w, "BedZ": bd, "S": s, "Curv": k, "BarW": br}
            for p, w, wd, bd, s, k, br in zip(chan, water, width, beds, cum, curv, bar)]
    st = shape.stats(chan)
    bends, on = 0, False
    for c in bend:
        if abs(c) > 0.4 and not on:
            bends += 1
        on = abs(c) > 0.4
    ratio = [wd / w for wd, w in zip(width, w0)]
    mean = sum(ratio) / len(ratio)
    ctx.notes.append("river %.0f m (sinuosity %.2f), %d bends, %d vertices carved" % (total / 100.0, st["sinuosity"],
                                                                                    bends, carved))
    return {"Terrain": terrain_out(), "River": [(WP.table_points(rows, TYPES), ["River"])],
            "Water": [(surface(chan, water, width, cum, flow_speed(water, ROW_CM)), ["Water"])],
            "Summary": _summary(length_m=total / 100.0, samples=len(chan), carved=carved,
                                monotone=all(b <= a + 1e-9 for a, b in zip(water, water[1:])),
                                width_min_cm=min(width), width_max_cm=max(width), water_drop_cm=water[0] - water[-1],
                                sinuosity=st["sinuosity"], straight_share=st["straight_share"],
                                max_turn_deg=st["max_turn_deg"], min_radius_m=st["min_radius_m"], bends=bends,
                                width_cv=math.sqrt(sum((x - mean) ** 2 for x in ratio) / len(ratio)) / mean)}
