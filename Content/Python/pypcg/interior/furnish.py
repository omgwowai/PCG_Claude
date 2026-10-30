"""PyInterior furnishing (spec 2026-10-28 §4.7): each room's recipe (catalog.RECIPES) placed on its clear floor by rules.

A room keeps three lists of rectangles: blocked (furniture), reserved (door swings and the approach to every passage) and
soft (the floor each placed piece needs in front of it). A piece may not overlap any of them; the floor in front of it may
overlap only soft and reserved floor. Wall pieces are tried against every side of the room, slid along it in STEP; centre
pieces on a grid around the room's middle. Each group scores its candidates by its own rules and takes the best (the seed
breaks ties):

- bed group: headboard on a wall, not the door's wall, preferably facing the door, centred, nightstands on both sides when
  they fit (one, or none, when not); a double bed when the room is wide enough, else a single;
- wardrobe: the widest that fits on a wall without a window, near a corner, preferably on the door's wall;
- sofa group: sofa on a wall with a free opposite wall 2.4-5 m away for the TV unit, the coffee table in between, a rug;
- dining group: the largest table that fits with chairs round it and room to pull them out;
- kitchen run: the grammar [F][C]*[K][C]*[S][C]* on the longest free stretch of wall (counters scale, the fridge never in
  front of a window), wall cabinets over the counters; a short wall takes [K][C]*[S] and the fridge elsewhere;
- bathing: a bathtub along a wall it spans from a corner, else a shower in a corner; vanity near the door, toilet not
  facing the door;
- single pieces (bookshelf, armchair, plant, shoe cabinet by the front door, ...): their own small rules.
A required group that cannot be placed is reported. Pure."""
import itertools
from dataclasses import dataclass

from pypcg.interior import catalog as C
from pypcg.interior import doors as D
from pypcg.interior import layout as L
from pypcg.interior.footprint import EPS, Rect
from pypcg.world import grammar as G

STEP = 10.0
GAP = 1.0                    # a wall piece stands this far off the wall face
YAW = {0: 0.0, 1: 90.0, 2: 180.0, 3: -90.0}       # back against side k (bottom, right, top, left) -> yaw
KITCHEN = {"F": "Fridge", "K": "Sink", "S": "Stove", "C": "Counter"}
KITCHEN_FULL = G.parse("[F][C]*[K][C]*[S][C]*")
KITCHEN_SHORT = G.parse("[K][C]*[S]")
UPPER_Z = 145.0
PULL = 60.0                  # room behind a dining chair, from the table edge
COMPACT_FRONT = 75.0         # a studio's kitchen run keeps this much working floor (a kitchen 90)


@dataclass
class Placement:
    item: str
    room: int
    x: float                 # footprint centre, house-local
    y: float
    yaw: float               # local, counter-clockwise; the piece's front points along (-sin yaw, cos yaw)
    w: float
    d: float
    h: float
    z: float = 0.0           # base height (wall cabinets)
    wall: int = -1           # the side of the room's clear floor it backs onto, -1 free standing
    group: str = ""

    def rect(self):
        if int(round(self.yaw)) % 180 == 0:
            return Rect(self.x - self.w / 2, self.y - self.d / 2, self.x + self.w / 2, self.y + self.d / 2)
        return Rect(self.x - self.d / 2, self.y - self.w / 2, self.x + self.d / 2, self.y + self.w / 2)

    def span(self):
        r = self.rect()
        return (r.x0, r.x1) if self.wall in (0, 2) else (r.y0, r.y1)


def side_line(R, k):
    return (R.x0, R.x1) if k in (0, 2) else (R.y0, R.y1)


def depth_across(R, k):
    return R.h if k in (0, 2) else R.w


def wall_rect(R, k, t, w, d, off=GAP):
    if k == 0:
        return Rect(t - w / 2, R.y0 + off, t + w / 2, R.y0 + off + d)
    if k == 2:
        return Rect(t - w / 2, R.y1 - off - d, t + w / 2, R.y1 - off)
    if k == 1:
        return Rect(R.x1 - off - d, t - w / 2, R.x1 - off, t + w / 2)
    return Rect(R.x0 + off, t - w / 2, R.x0 + off + d, t + w / 2)


def front_rect(R, k, t, w, d, depth, off=GAP):
    return wall_rect(R, k, t, w, depth, off + d)


def on_side(room, k, axis, c, plan):
    """Whether the wall line (axis, c) is side k of the room."""
    r = room.rect
    line = {0: ("y", r.y0), 1: ("x", r.x1), 2: ("y", r.y1), 3: ("x", r.x0)}[k]
    return line[0] == axis and abs(line[1] - c) < EPS


def side_of(room, axis, c):
    for k in range(4):
        if on_side(room, k, axis, c, None):
            return k
    return None


PATH = 90.0                  # the walkway through a wide opening: its middle this wide is kept free
LANDING = 100.0              # the floor in front of a stair opening, its whole width (spec 2026-10-29)


def approach(door, room, plan):
    """The floor of `room` in front of a passage it does not swing into: D.APPROACH deep, as wide as the passage -- for a
    wide opening only its middle PATH, the walkway through it; before a stair opening LANDING deep over all of it."""
    R = room.rect
    s0, s1 = door.s0, door.s1
    depth = D.APPROACH
    if door.kind == "stair":
        depth = LANDING
    elif s1 - s0 > PATH:
        m = 0.5 * (s0 + s1)
        s0, s1 = m - 0.5 * PATH, m + 0.5 * PATH
    if door.axis == "x":
        if R.x0 >= door.c - EPS:
            return Rect(door.c, s0, min(R.x1, door.c + depth + 0.5 * plan.walls["int"]), s1)
        return Rect(max(R.x0, door.c - depth - 0.5 * plan.walls["int"]), s0, door.c, s1)
    t = plan.walls["ext"] if door.kind == "front" else 0.5 * plan.walls["int"]
    if R.y0 >= door.c - EPS:
        return Rect(s0, door.c, s1, min(R.y1, door.c + depth + t))
    return Rect(s0, max(R.y0, door.c - depth - t), s1, door.c)


def _overlap(a0, a1, b0, b1):
    return a0 < b1 - EPS and b0 < a1 - EPS


class RoomCtx:
    def __init__(self, room, plan, doors, wins, rng):
        self.room, self.plan, self.rng = room, plan, rng
        self.R = L.clear_rect(room.rect, plan.footprint, plan.walls)
        self.blocked, self.reserved, self.soft = [], [], []
        self.passages = {k: [] for k in range(4)}
        self.windows = {k: [] for k in range(4)}
        self.entry_side = None
        self.front_door = None
        for d in doors:
            if room.id not in (d.a, d.b):
                continue
            k = side_of(room, d.axis, d.c)
            if k is None:
                continue
            self.passages[k].append((d.s0, d.s1))
            zone = D.swing(d, room, plan) if (d.leaf and d.b == room.id) else approach(d, room, plan)
            self.reserved.append(zone)
            if d.b == room.id and d.tree:
                self.entry_side = k
            if d.kind == "front":
                self.front_door = (k, d)
        for w in wins:
            if w.room == room.id:
                k = side_of(room, w.axis, w.c)
                if k is not None:
                    self.windows[k].append((w.s0, w.s1, w.sill))

    def jitter(self):
        return self.rng.random() * 1e-3

    def fits(self, rect, front=None, k=None, span=None, tall=False, ignore=()):
        """`tall`: False, or the piece's height -- it may not stand before a window whose sill is lower."""
        if not rect.inside(self.R):
            return False
        for b in self.blocked + self.reserved + self.soft:
            if b not in ignore and rect.overlaps(b):
                return False
        if front is not None:
            if not front.inside(self.R):
                return False
            for b in self.blocked:
                if b not in ignore and front.overlaps(b):
                    return False
        if k is not None and span is not None:
            lo, hi = span
            for a, b in self.passages[k]:
                if _overlap(lo, hi, a, b):
                    return False
            if tall:
                for a, b, sill in self.windows[k]:
                    if _overlap(lo, hi, a, b) and (tall is True or tall > sill + EPS):
                        return False
        return True

    def window_overlap(self, k, lo, hi):
        return sum(max(0.0, min(hi, b) - max(lo, a)) for a, b, _s in self.windows[k])

    def spots(self, k, w):
        lo, hi = side_line(self.R, k)
        if hi - lo < w - EPS:
            return []
        out, t = [], lo + w / 2
        while t <= hi - w / 2 + EPS:
            out.append(t)
            t += STEP
        if not out or abs(out[-1] - (hi - w / 2)) > EPS:
            out.append(hi - w / 2)
        return out

    def corner_dist(self, k, t, w):
        lo, hi = side_line(self.R, k)
        return min(t - w / 2 - lo, hi - (t + w / 2))

    def put(self, out, item, rect, yaw, k, group, z=0.0, front=None, block=True):
        it = C.ITEMS[item]
        out.append(Placement(item, self.room.id, rect.cx, rect.cy, yaw, it.w, it.d, it.h, z, k, group))
        if block and it.kind != "rug" and z < 100.0:
            self.blocked.append(rect)
        if front is not None:
            self.soft.append(front)
        return out[-1]


def _opp(k):
    return None if k is None else (k + 2) % 4


# ---------------------------------------------------------------- single wall pieces

def wall_piece(ctx, out, item, group, prefer=None, near_door=False, near_corner=True, window=0.0, ignore=()):
    """Place one wall piece; prefer: a side to favour; near_door: close to the room's passages; window: a bonus per cm
    of window behind it (negative: a penalty)."""
    it = C.ITEMS[item]
    best = None
    for k in range(4):
        for t in ctx.spots(k, it.w):
            rect = wall_rect(ctx.R, k, t, it.w, it.d)
            front = front_rect(ctx.R, k, t, it.w, it.d, it.front) if it.front else None
            span = (t - it.w / 2, t + it.w / 2)
            if not ctx.fits(rect, front, k, span, it.h if it.tall else False, ignore=ignore):
                continue
            s = 0.0
            if near_corner:
                s += ctx.corner_dist(k, t, it.w) / 300.0
            if prefer is not None and k == prefer:
                s -= 1.0
            if near_door and ctx.passages[k]:
                s += min(abs(t - 0.5 * (a + b)) for a, b in ctx.passages[k]) / 300.0
            elif near_door:
                s += 2.0
            s -= window * ctx.window_overlap(k, *span) / 100.0
            s += ctx.jitter()
            if best is None or s < best[0]:
                best = (s, k, t, rect, front)
    if best is None:
        return None
    _s, k, t, rect, front = best
    return ctx.put(out, item, rect, YAW[k], k, group, front=front)


def corner_piece(ctx, out, item, group):
    it = C.ITEMS[item]
    R = ctx.R
    best = None
    for cx, cy in ((R.x0 + it.w / 2 + GAP, R.y0 + it.d / 2 + GAP), (R.x1 - it.w / 2 - GAP, R.y0 + it.d / 2 + GAP),
                   (R.x1 - it.w / 2 - GAP, R.y1 - it.d / 2 - GAP), (R.x0 + it.w / 2 + GAP, R.y1 - it.d / 2 - GAP)):
        rect = Rect(cx - it.w / 2, cy - it.d / 2, cx + it.w / 2, cy + it.d / 2)
        if not ctx.fits(rect):
            continue
        s = ctx.jitter()
        if best is None or s < best[0]:
            best = (s, rect)
    if best is None:
        return None
    # face the room's middle
    rect = best[1]
    dx, dy = R.cx - rect.cx, R.cy - rect.cy
    yaw = 0.0 if abs(dy) >= abs(dx) and dy > 0 else (180.0 if abs(dy) >= abs(dx) else (-90.0 if dx > 0 else 90.0))
    if int(round(yaw)) % 180:
        rect = Rect(rect.cx - it.d / 2, rect.cy - it.w / 2, rect.cx + it.d / 2, rect.cy + it.w / 2)
        if not ctx.fits(rect):
            yaw, rect = 0.0, best[1]
    return ctx.put(out, item, rect, yaw, -1, group)


# ---------------------------------------------------------------- groups

def bed_group(ctx, out, rtype):
    R = ctx.R
    if rtype == "Main" and daybed(ctx, out):           # a studio sleeps on a day bed along a wall first
        return True
    if rtype == "Master":
        beds = ["Bed_King", "Bed_Double"]
    elif rtype == "Main":
        beds = ["Bed_Double", "Bed_Single"] if R.short >= 300 else ["Bed_Single"]
    else:
        beds = ["Bed_Double", "Bed_Single"] if R.short >= 290 else ["Bed_Single", "Bed_Double"]
    ns = C.ITEMS["Nightstand"]
    for bed in beds:
        it = C.ITEMS[bed]
        for n in (2, 1, 0):
            gw = it.w + n * (ns.w + 4.0)
            best = None
            for k in range(4):
                for t in ctx.spots(k, gw):
                    grp = wall_rect(R, k, t, gw, it.d)
                    span = (t - gw / 2, t + gw / 2)
                    bt = t if n != 1 else t + (ns.w + 4.0) / 2 * (1 if (t - R.cx if k in (0, 2) else t - R.cy) < 0 else -1)
                    front = front_rect(R, k, bt, it.w, it.d, it.front)
                    if not ctx.fits(grp, front, k, span):
                        continue
                    s = 0.0
                    if k == ctx.entry_side:
                        s += 4.0
                    if k == _opp(ctx.entry_side):
                        s -= 1.5
                    lo, hi = side_line(R, k)
                    s += abs(t - 0.5 * (lo + hi)) / 200.0
                    s += 2.0 * ctx.window_overlap(k, *span) / max(gw, 1.0)
                    if bed == "Bed_Single":
                        s += ctx.corner_dist(k, t, gw) / 400.0
                    s += ctx.jitter()
                    if best is None or s < best[0]:
                        best = (s, k, t, bt)
            if best is None:
                continue
            _s, k, t, bt = best
            rect = wall_rect(R, k, bt, it.w, it.d)
            ctx.put(out, bed, rect, YAW[k], k, "bed_group", front=front_rect(R, k, bt, it.w, it.d, it.front))
            for side in (-1, 1):
                if n == 0 or (n == 1 and (side < 0) != (bt > t)):
                    continue
                nt = bt + side * (it.w / 2 + 2.0 + ns.w / 2)
                ctx.put(out, "Nightstand", wall_rect(R, k, nt, ns.w, ns.d), YAW[k], k, "bed_group")
            return True
    if rtype == "Bedroom":
        return daybed(ctx, out)
    return False


def daybed(ctx, out):
    """A single bed with its long side to the wall (a studio's day bed): the last resort of a small room."""
    it = C.ITEMS["Bed_Single"]
    best = None
    for k in range(4):
        for t in ctx.spots(k, it.d):
            rect = wall_rect(ctx.R, k, t, it.d, it.w)
            front = front_rect(ctx.R, k, t, it.d, it.w, 50.0)
            if not ctx.fits(rect, front, k, (t - it.d / 2, t + it.d / 2)):
                continue
            s = ctx.corner_dist(k, t, it.d) / 200.0 + ctx.jitter()
            if best is None or s < best[0]:
                best = (s, k, rect, front)
    if best is None:
        return False
    _s, k, rect, front = best
    ctx.put(out, "Bed_Single", rect, YAW[k] + 90.0, k, "bed_group", front=front)
    return True


def wardrobe(ctx, out):
    for w in ("Wardrobe_200", "Wardrobe_150", "Wardrobe_100"):
        if wall_piece(ctx, out, w, "wardrobe", prefer=ctx.entry_side):
            return True
    return False


def desk_group(ctx, out):
    p = wall_piece(ctx, out, "Desk", "desk_group", window=2.0)
    if p is None:
        return False
    ch = C.ITEMS["Chair"]
    k = p.wall
    t = p.rect().cx if k in (0, 2) else p.rect().cy
    rect = front_rect(ctx.R, k, t, ch.w, p.d - 15.0, ch.d)
    ctx.put(out, "Chair", rect, YAW[k] + 180.0, -1, "desk_group")
    return True


def sofa_group(ctx, out, compact=False):
    R = ctx.R
    tv, table = C.ITEMS["TVUnit"], C.ITEMS["CoffeeTable"]
    for sofa in (("Sofa_Small",) if compact else ("Sofa", "Sofa_Small")):
        it = C.ITEMS[sofa]
        best = None
        for k in range(4):
            opp = _opp(k)
            across = depth_across(R, k)
            gap = across - it.d - tv.d - 2 * GAP
            for t in ctx.spots(k, it.w):
                rect = wall_rect(R, k, t, it.w, it.d)
                front = front_rect(R, k, t, it.w, it.d, it.front)
                span = (t - it.w / 2, t + it.w / 2)
                if not ctx.fits(rect, front, k, span):
                    continue
                s = 0.0
                tv_ok = False
                if 160.0 <= gap <= 450.0:
                    trect = wall_rect(R, opp, t, tv.w, tv.d)
                    tv_ok = ctx.fits(trect, front_rect(R, opp, t, tv.w, tv.d, tv.front), opp, (t - tv.w / 2, t + tv.w / 2),
                                     tv.h, ignore=(front,))
                if tv_ok:
                    s -= 3.0
                if k == ctx.entry_side:
                    s += 2.0
                lo, hi = side_line(R, k)
                s += abs(t - 0.5 * (lo + hi)) / 250.0
                s += 0.5 * ctx.window_overlap(k, *span) / it.w
                s += ctx.jitter()
                if best is None or s < best[0]:
                    best = (s, k, t, rect, front, tv_ok, gap)
        if best is None:
            continue
        _s, k, t, rect, front, tv_ok, gap = best
        ctx.put(out, sofa, rect, YAW[k], k, "sofa_group", front=front)
        opp = _opp(k)
        if tv_ok:
            trect = wall_rect(R, opp, t, tv.w, tv.d)
            ctx.put(out, "TVUnit", trect, YAW[opp], opp, "sofa_group", front=front_rect(R, opp, t, tv.w, tv.d, tv.front))
        # the coffee table 40 cm in front of the sofa, the rug under it
        if gap >= table.d + 120.0:
            crect = front_rect(R, k, t, table.w, it.d + 40.0, table.d)
            if ctx.fits(crect, ignore=(front,)):
                ctx.put(out, "CoffeeTable", crect, YAW[k], -1, "sofa_group")
        for rug in ("Rug_Large", "Rug_Small"):
            ru = C.ITEMS[rug]
            rr = front_rect(R, k, t, ru.w, it.d - 30.0, ru.d)
            if rr.inside(R) and not any(rr.overlaps(z) for z in ctx.reserved):
                ctx.put(out, rug, rr, YAW[k], -1, "sofa_group", block=False)
                break
        return True
    return False


def _chairs(table_rect, n_long, along_x):
    """Chair rectangles round a table: n_long on each long side, facing it (yaw so the chair's front faces the table)."""
    ch = C.ITEMS["Chair"]
    out = []
    T = table_rect
    if along_x:
        for k in range(n_long):
            x = T.x0 + T.w * (k + 0.5) / n_long
            out.append((Rect(x - ch.w / 2, T.y0 - ch.d + 15, x + ch.w / 2, T.y0 + 15), 0.0))      # below, facing +y
            out.append((Rect(x - ch.w / 2, T.y1 - 15, x + ch.w / 2, T.y1 + ch.d - 15), 180.0))
    else:
        for k in range(n_long):
            y = T.y0 + T.h * (k + 0.5) / n_long
            out.append((Rect(T.x0 - ch.d + 15, y - ch.w / 2, T.x0 + 15, y + ch.w / 2), -90.0))
            out.append((Rect(T.x1 - 15, y - ch.w / 2, T.x1 + ch.d - 15, y + ch.w / 2), 90.0))
    return out


def dining_group(ctx, out, tables=("Table_6", "Table_4", "Table_2")):
    R = ctx.R
    for name in tables:
        it = C.ITEMS[name]
        n = {"Table_6": 3, "Table_4": 2, "Table_2": 1}[name]
        best = None
        along_x = R.w >= R.h
        tw, td = (it.w, it.d) if along_x else (it.d, it.w)
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                cx, cy = R.cx + dx * 20.0, R.cy + dy * 20.0
                T = Rect(cx - tw / 2, cy - td / 2, cx + tw / 2, cy + td / 2)
                pull = Rect(T.x0 - (0 if along_x else PULL), T.y0 - (PULL if along_x else 0),
                            T.x1 + (0 if along_x else PULL), T.y1 + (PULL if along_x else 0))
                if not ctx.fits(T) or not pull.inside(R):
                    continue
                chairs = _chairs(T, n, along_x)
                if not all(ctx.fits(c) for c, _y in chairs):
                    continue
                if any(pull.overlaps(b) for b in ctx.blocked):      # pulling a chair out may cross a walkway
                    continue
                s = abs(dx) + abs(dy) + ctx.jitter()
                if best is None or s < best[0]:
                    best = (s, T, chairs)
        if best is None:
            continue
        _s, T, chairs = best
        ctx.put(out, name, T, 0.0 if along_x else 90.0, -1, "dining_group")
        for c, yaw in chairs:
            ctx.put(out, "Chair", c, yaw, -1, "dining_group")
        return True
    return False


def _free_stretches(ctx, k, depth, front):
    """Maximal stretches along side k where a `depth` deep run with `front` floor before it fits."""
    lo, hi = side_line(ctx.R, k)
    out, start, t = [], None, lo
    while t + STEP <= hi + EPS:
        rect = wall_rect(ctx.R, k, t + STEP / 2, STEP, depth)
        fr = front_rect(ctx.R, k, t + STEP / 2, STEP, depth, front)
        ok = ctx.fits(rect, fr, k, (t, t + STEP))
        if ok and start is None:
            start = t
        if not ok and start is not None:
            out.append((start, t))
            start = None
        t += STEP
    if start is not None:
        out.append((start, t))
    return out


def _snapshot(ctx, out):
    return (list(ctx.blocked), list(ctx.soft), len(out))


def _restore(ctx, out, snap):
    ctx.blocked[:], ctx.soft[:] = snap[0], snap[1]
    del out[snap[2]:]


def _lay_run(ctx, out, k, mods, work):
    R = ctx.R
    for sym, x0, x1 in mods:
        name = KITCHEN[sym]
        it = C.ITEMS[name]
        w = x1 - x0
        rect = wall_rect(R, k, 0.5 * (x0 + x1), w, it.d)
        out.append(Placement(name, ctx.room.id, rect.cx, rect.cy, YAW[k], w, it.d, it.h, 0.0, k, "kitchen_run"))
        ctx.blocked.append(rect)
        ctx.soft.append(front_rect(R, k, 0.5 * (x0 + x1), w, it.d, work))
        # wall cabinets over counters, sink and stove, not over a window
        if sym != "F" and not ctx.window_overlap(k, x0, x1):
            up = "UpperCab_80" if w > 70 else "UpperCab_60"
            u = C.ITEMS[up]
            ur = wall_rect(R, k, 0.5 * (x0 + x1), w, u.d)
            out.append(Placement(up, ctx.room.id, ur.cx, ur.cy, YAW[k], w, u.d, u.h, UPPER_Z, k, "kitchen_run"))


def _try_runs(ctx, out, grammar, need, stretches, widths, work, then=None):
    """Lay `grammar` on the first stretch it fits, either way round (the fridge never before a window); `then`: what must
    still fit after the run, else the run is undone and the next one tried."""
    for length, k, a, b in stretches:
        if length < need - EPS:
            continue
        # slack: what no whole counter fills stays an empty gap at the run's end -- never a 10 cm counter
        res = G.solve(grammar, length, widths, {"C"}, ctx.rng, smin=0.5, smax=3.0, slack=True)
        if not res["symbols"] or not res["ok"]:
            continue
        pos = G.positions(res, widths, {"C"})
        mods = [(sym, a + x0, a + x1) for sym, (x0, x1) in zip(res["symbols"], pos)]
        for flip in (False, True):
            run = [(sym, a + b - x1, a + b - x0) for sym, x0, x1 in mods] if flip else mods
            if any(sym == "F" and ctx.window_overlap(k, x0, x1) > 0 for sym, x0, x1 in run):
                continue
            snap = _snapshot(ctx, out)
            _lay_run(ctx, out, k, run, work)
            if then is None or then():
                return True
            _restore(ctx, out, snap)
    return False


def _fridge_spots(ctx, limit=16):
    """The places the fridge can stand on its own, nearest a corner first: (corner distance, side, t, rect, front)."""
    it = C.ITEMS["Fridge"]
    found = []
    for k in range(4):
        for t in ctx.spots(k, it.w):
            rect = wall_rect(ctx.R, k, t, it.w, it.d)
            front = front_rect(ctx.R, k, t, it.w, it.d, it.front)
            if ctx.fits(rect, front, k, (t - it.w / 2, t + it.w / 2), it.h):
                found.append((ctx.corner_dist(k, t, it.w), k, t, rect, front))
    found.sort(key=lambda s: s[:3])
    return found[:limit]


def kitchen_run(ctx, out, compact=False, shortest_first=False):
    """The run on a free stretch of wall. First the full grammar on every stretch (longest first, or shortest first), the
    fridge at whichever end has no window; then the short grammar with the fridge on its own after it; then the fridge
    first, at each place it can stand, and the short run on what is left (a kitchen whose one window-free corner both
    want); last the three pieces on their own, in every order. A run that cannot be placed leaves the room as it was."""
    depth = max(C.ITEMS[n].d for n in KITCHEN.values())     # the deepest module (the fridge) decides the free stretch
    widths = {s: C.ITEMS[n].w for s, n in KITCHEN.items()}
    work = COMPACT_FRONT if compact else C.ITEMS["Counter"].front

    def stretches():
        found = [(b - a, k, a, b) for k in range(4) for a, b in _free_stretches(ctx, k, depth, work)]
        found.sort(key=lambda s: ((s[0] if shortest_first else -s[0]), s[1]))
        return found

    if _try_runs(ctx, out, KITCHEN_FULL, widths["F"] + widths["K"] + widths["S"], stretches(), widths, work):
        return True
    short = widths["K"] + widths["S"]
    # the fridge of a short run stands on its own, typically at the run's corner, in the counters' working floor
    if _try_runs(ctx, out, KITCHEN_SHORT, short, stretches(), widths, work,
                 then=lambda: wall_piece(ctx, out, "Fridge", "kitchen_run", ignore=tuple(ctx.soft)) is not None):
        return True
    for _d, k, _t, rect, front in _fridge_spots(ctx):
        snap = _snapshot(ctx, out)
        ctx.put(out, "Fridge", rect, YAW[k], k, "kitchen_run", front=front)
        if _try_runs(ctx, out, KITCHEN_SHORT, short, stretches(), widths, work):
            return True
        _restore(ctx, out, snap)
    for order in itertools.permutations(("Sink", "Stove", "Fridge")):
        snap = _snapshot(ctx, out)
        if all(wall_piece(ctx, out, name, "kitchen_run", near_corner=False) is not None for name in order):
            return True
        _restore(ctx, out, snap)
    return False


def island(ctx, out):
    it = C.ITEMS["Island"]
    R = ctx.R
    if R.short < it.d + 2 * 100 + 62 or R.long < it.w + 2 * 100:
        return False
    rect = Rect(R.cx - it.w / 2, R.cy - it.d / 2, R.cx + it.w / 2, R.cy + it.d / 2)
    if R.h > R.w:
        rect = Rect(R.cx - it.d / 2, R.cy - it.w / 2, R.cx + it.d / 2, R.cy + it.w / 2)
    ring = rect.shrink(-100, -100, -100, -100)
    if not ctx.fits(rect) or any(ring.overlaps(b) for b in ctx.blocked + ctx.reserved):
        return False
    ctx.put(out, "Island", rect, 0.0 if R.w >= R.h else 90.0, -1, "island")
    return True


def bathing(ctx, out, shower_only=False):
    R = ctx.R
    tub = C.ITEMS["Bathtub"]
    best = None
    if shower_only:
        return _shower(ctx, out)
    for k in range(4):
        lo, hi = side_line(R, k)
        for t in (lo + tub.w / 2 + GAP, hi - tub.w / 2 - GAP):
            rect = wall_rect(R, k, t, tub.w, tub.d)
            front = front_rect(R, k, t, tub.w, tub.d, tub.front)
            if not ctx.fits(rect, front, k, (t - tub.w / 2, t + tub.w / 2)):
                continue
            s = (hi - lo - tub.w) / 100.0 + (2.0 if k == ctx.entry_side else 0.0) + ctx.jitter()
            if best is None or s < best[0]:
                best = (s, k, t, rect, front)
    if best is not None:
        _s, k, t, rect, front = best
        ctx.put(out, "Bathtub", rect, YAW[k], k, "bathing", front=front)
        return True
    return _shower(ctx, out)


def _shower(ctx, out):
    R = ctx.R
    sh = C.ITEMS["Shower"]
    for k in sorted(range(4), key=lambda k: (k == ctx.entry_side, k)):
        lo, hi = side_line(R, k)
        for t, flip in ((lo + sh.w / 2 + GAP, False), (hi - sh.w / 2 - GAP, True)):
            rect = wall_rect(R, k, t, sh.w, sh.d)
            if ctx.fits(rect, front_rect(R, k, t, sh.w, sh.d, sh.front), k, (t - sh.w / 2, t + sh.w / 2), sh.h):
                ctx.put(out, "Shower", rect, YAW[k], k, "bathing", front=front_rect(R, k, t, sh.w, sh.d, sh.front))
                return True
    return False


def toilet(ctx, out, item="Toilet"):
    it = C.ITEMS[item]
    best = None
    for k in range(4):
        for t in ctx.spots(k, it.w + 30.0):
            rect = wall_rect(ctx.R, k, t, it.w, it.d)
            side = wall_rect(ctx.R, k, t, it.w + 30.0, it.d)       # elbow room: clear of furniture only
            front = front_rect(ctx.R, k, t, it.w, it.d, it.front)
            if not ctx.fits(rect, front, k, (t - it.w / 2, t + it.w / 2)) or not side.inside(ctx.R) or                     any(side.overlaps(b) for b in ctx.blocked):
                continue
            s = 0.0
            if k == _opp(ctx.entry_side) and any(_overlap(t - 40, t + 40, a, b) for a, b in ctx.passages[_opp(k)]):
                s += 3.0                     # facing the door
            s += ctx.corner_dist(k, t, it.w + 30.0) / 200.0 + ctx.jitter()
            if best is None or s < best[0]:
                best = (s, k, t, rect, front)
    if best is None:
        return None
    _s, k, t, rect, front = best
    return ctx.put(out, item, rect, YAW[k], k, item.lower(), front=front)


def dining_small(ctx, out):
    return dining_group(ctx, out, ("Table_2",))


def _do(ctx, out, step, rtype, plan):
    if step == "bed_group":
        return bed_group(ctx, out, rtype)
    if step == "wardrobe":
        return wardrobe(ctx, out)
    if step == "desk_group":
        cr = ctx.R
        return desk_group(ctx, out) if rtype == "Study" or cr.w * cr.h >= 90000.0 else False
    if step == "sofa_group":
        return sofa_group(ctx, out, compact=(rtype == "Main"))
    if step == "dining_group":
        return dining_group(ctx, out)
    if step == "dining_small":
        if rtype == "Kitchen" and any(r.type == "Dining" for r in plan.rooms):
            return False
        return dining_small(ctx, out)
    if step == "kitchen_run":
        return kitchen_run(ctx, out, compact=(rtype == "Main"))
    if step == "kitchen_short_wall":
        return kitchen_run(ctx, out, compact=(rtype == "Main"), shortest_first=True)
    if step == "island":
        return island(ctx, out)
    if step == "bathing":
        return bathing(ctx, out)
    if step == "shower":
        return bathing(ctx, out, shower_only=True)
    if step in ("Toilet",):
        return toilet(ctx, out) is not None
    if step == "ShoeCabinet":
        if ctx.front_door is None:
            return False
        return wall_piece(ctx, out, step, "entry", prefer=ctx.front_door[0], near_door=True) is not None
    if step in ("Plant", "FloorLamp", "Armchair"):
        return corner_piece(ctx, out, step, "decor") is not None
    if step in ("Vanity", "Basin"):
        return wall_piece(ctx, out, step, "vanity", prefer=ctx.entry_side, near_door=True) is not None
    if step == "Console":
        if ctx.R.short < 120.0:
            return False
        return wall_piece(ctx, out, step, "decor") is not None
    return wall_piece(ctx, out, step, step.lower()) is not None


# a step that may stand in for another when the room is tight
ALTERNATES = {"bathing": ("bathing", "shower"), "Vanity": ("Vanity", "Basin"),
              "kitchen_run": ("kitchen_run", "kitchen_short_wall")}


def attempts(recipe):
    """The recipe, then its required steps in every other order (optional steps keep their place after them), then the
    same with each alternate -- the order a room is tried in until every required piece fits."""
    import itertools
    req = [s for s, r in recipe if r]
    opt = [(s, r) for s, r in recipe if not r]
    seen, out = set(), []
    alts = [list(dict.fromkeys(ALTERNATES.get(s, (s,)))) for s in req]
    for choice in itertools.product(*alts):
        for order in itertools.permutations(choice):
            key = tuple(order)
            if key not in seen:
                seen.add(key)
                out.append([(s, True) for s in order] + opt)
    return out


def furnish(plan, doors, wins, rng):
    """([Placement], [failure]) for the whole house: each room's recipe, tried in other orders while a required piece does
    not fit (attempts), the first attempt that places them all -- or the one that places the most."""
    out, fails = [], []
    for room in plan.rooms:
        best = None
        for recipe in attempts(C.RECIPES.get(room.type, ())):
            ctx = RoomCtx(room, plan, doors, wins, rng)
            placed, missing = [], []
            for step, required in recipe:
                if not _do(ctx, placed, step, room.type, plan) and required:
                    missing.append(step)
            if best is None or len(missing) < len(best[1]):
                best = (placed, missing)
            if not missing:
                break
        out += best[0]
        fails += ["%s %d: no %s" % (room.type, room.id, step) for step in best[1]]
    return out, fails
