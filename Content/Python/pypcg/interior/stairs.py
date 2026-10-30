"""PyInterior stairs (spec 2026-10-29 §6): the stair room of a multi-storey house -- its types, where it may stand, its
openings on each floor and (Task 9) its parts.

A stair is a room placed before any floor is planned, at the same place on every floor, inside the top floor (which every
lower floor contains) and against a wall that is outside on every floor. Its own frame: u runs from the opening end into
the stair (the first flight climbs along +u from u = 0), v across it; `orient` 0..3 points u along +y, -x, -y, +x of the
house. Flights are 100 wide with 27 cm treads; a floor's H is climbed in ceil(H / 18) risers (17 for 300 cm).

  U         two flights side by side (A: v 0..W/2 up from u = 0, B: back down the other half), a landing across the far end;
            leaves from and arrives at the same end -- stacks for three floors
  L         flight A along u, a corner landing, flight B along +v; arrives on the v = W side at the far corner
  Straight  one flight along u; arrives at the far end
Parts (§8): tread blocks a riser plus UNDER thick (their undersides a sawtooth), landings LANDING_T thick, in the style's
wood; a handrail along each flight; the U's top floor a guard rail along the open half of its opening. Pure."""
import math
from dataclasses import dataclass

from pypcg.interior import floorplan as FP
from pypcg.interior import layout as L
from pypcg.interior import terrace as T
from pypcg.interior.footprint import EPS, Rect

TREAD = 27.0
FLIGHT_W = 100.0
RISE_MAX = 18.0
SNAP = 10.0
GAP = 10.0                   # between the U's two flights
UNDER = 15.0                 # a tread block reaches this far below the riser under it
LANDING_T = 20.0
RAIL_UP = 90.0               # a handrail above the line of the nosings
HAND_T = 5.0


@dataclass(frozen=True)
class StairType:
    name: str
    clear_w: float           # across the flights (v)
    clear_l: float           # along the first flight (u)
    max_floors: int


TYPES = {"U": StairType("U", 220.0, 330.0, 3), "L": StairType("L", 300.0, 330.0, 2),
         "Straight": StairType("Straight", 110.0, 450.0, 2)}
ORDER = ("U", "L", "Straight")

# the house side each side of the stair lies on, per orientation
SIDES = {0: {"u0": "y0", "uL": "y1", "v0": "x0", "vW": "x1"}, 1: {"u0": "x1", "uL": "x0", "v0": "y0", "vW": "y1"},
         2: {"u0": "y1", "uL": "y0", "v0": "x1", "vW": "x0"}, 3: {"u0": "x0", "uL": "x1", "v0": "y1", "vW": "y0"}}


def roles(n_floors):
    return ["ground"] + ["middle"] * (n_floors - 2) + ["top"] if n_floors > 1 else ["ground"]


def opening(kind, role):
    """(stair side, a0, a1): where the stair opens on a floor of this role (a0..a1 along that side, stair coordinates)."""
    t = TYPES[kind]
    if kind == "U":
        return ("u0", 0.0, t.clear_w / 2) if role == "ground" else ("u0", 0.0, t.clear_w)
    if role == "middle":
        raise ValueError("a %s stair serves two floors" % kind)
    if kind == "Straight":
        return ("u0", 0.0, t.clear_w) if role == "ground" else ("uL", 0.0, t.clear_w)
    # L: up flight A from the near end; off flight B at the far corner of the turn side
    return ("u0", 0.0, FLIGHT_W + 10.0) if role == "ground" else ("vW", t.clear_l - FLIGHT_W - 10.0, t.clear_l)


def _up(v):
    return math.ceil(v / SNAP - 1e-9) * SNAP


def _down(v):
    return math.floor(v / SNAP + 1e-9) * SNAP


@dataclass(frozen=True)
class Stair:
    type: str
    rect: Rect               # the stair room on partition lines, house-local
    clear: Rect              # inside its walls
    orient: int
    n_floors: int

    @property
    def dims(self):
        t = TYPES[self.type]
        return t.clear_w, t.clear_l

    def role(self, level):
        return "ground" if level == 0 else ("top" if level == self.n_floors - 1 else "middle")

    def to_local(self, u, v):
        c, o = self.clear, self.orient
        if o == 0:
            return (c.x0 + v, c.y0 + u)
        if o == 1:
            return (c.x1 - u, c.y0 + v)
        if o == 2:
            return (c.x1 - v, c.y1 - u)
        return (c.x0 + u, c.y1 - v)

    def side_line(self, side):
        """(axis, c, outward) of one side of the stair room ("u0", "uL", "v0", "vW") on its partition line."""
        r = self.rect
        return {"x0": ("x", r.x0, -1), "x1": ("x", r.x1, 1), "y0": ("y", r.y0, -1),
                "y1": ("y", r.y1, 1)}[SIDES[self.orient][side]]

    def span(self, side, a0, a1):
        """(axis, c, s0, s1): a stretch a0..a1 of one stair side on its partition line, house-local."""
        axis, c, _out = self.side_line(side)
        w, l = self.dims
        if side in ("u0", "uL"):
            ue = 0.0 if side == "u0" else l
            p, q = self.to_local(ue, a0), self.to_local(ue, a1)
        else:
            ve = 0.0 if side == "v0" else w
            p, q = self.to_local(a0, ve), self.to_local(a1, ve)
        k = 0 if axis == "y" else 1
        lo, hi = sorted((p[k], q[k]))
        return (axis, c, lo, hi)

    def access(self, role):
        """(axis, c, s0, s1): the stair's opening on a floor of this role."""
        return self.span(*opening(self.type, role))

    def access_outward(self, role):
        return self.side_line(opening(self.type, role)[0])[2]

    def void(self, role):
        """The U's top floor: flight A's half of the open end, open over the flight below (a guard rail goes there)."""
        if self.type == "U" and role == "top":
            return self.span("u0", 0.0, self.dims[0] / 2)
        return None

    def cells(self, grid):
        r = self.rect
        return frozenset((i, j) for i in range(int(math.floor(r.x0 / grid + 1e-9)), int(math.ceil(r.x1 / grid - 1e-9)))
                         for j in range(int(math.floor(r.y0 / grid + 1e-9)), int(math.ceil(r.y1 / grid - 1e-9))))


# ---------------------------------------------------------------- candidates

def _wall_side(seg):
    """The side of a room that lies on this outline segment (the footprint is on the segment's inner side)."""
    if seg.axis == "y":
        return "y0" if seg.normal < 0 else "y1"
    return "x1" if seg.normal > 0 else "x0"


def _room_rect(seg, side, dx, dy, place, walls):
    """The stair room on partition lines for clear extents dx, dy with one side on `seg`, at its start, end or middle."""
    ext, half = walls["ext"], 0.5 * walls["int"]
    along, depth = (dx, dy) if seg.axis == "y" else (dy, dx)
    if side in ("y0", "x0"):
        c0, c1 = seg.c, _up(seg.c + ext + depth + half)
    else:
        c0, c1 = _down(seg.c - ext - depth - half), seg.c
    if place == "start":
        a0, a1 = seg.a0, _up(seg.a0 + (ext if seg.convex0 else half) + along + half)
    elif place == "end":
        a0, a1 = _down(seg.a1 - (ext if seg.convex1 else half) - along - half), seg.a1
    else:
        size = _up(along + 2 * half)
        a0 = _down(0.5 * (seg.a0 + seg.a1) - 0.5 * size)
        a1 = a0 + size
    if a0 < seg.a0 - EPS or a1 > seg.a1 + EPS:
        return None
    return Rect(a0, c0, a1, c1) if seg.axis == "y" else Rect(c0, a0, c1, a1)


def _clear(r, fps, walls):
    """The room's clear rectangle: an exterior wall's thickness on a side outside on any floor, half an interior wall else."""
    ext, half = walls["ext"], 0.5 * walls["int"]

    def allow(axis, c, a0, a1, out):
        return ext if any(L.exterior_parts(fp, axis, c, a0, a1, out) for fp in fps) else half
    return r.shrink(allow("x", r.x0, r.y0, r.y1, -1), allow("y", r.y0, r.x0, r.x1, -1),
                    allow("x", r.x1, r.y0, r.y1, 1), allow("y", r.y1, r.x0, r.x1, 1))


def _outside_everywhere(fps, axis, c, a0, a1, out):
    return all(abs(sum(b - a for a, b in L.exterior_parts(fp, axis, c, a0, a1, out)) - (a1 - a0)) < 1e-6 for fp in fps)


def _score(st, fps):
    g = fps[0]
    bb = g.bbox()
    ext = max(bb.w, bb.h)
    s = 0.0
    if any(seg.axis == "y" and seg.normal < 0 and abs(st.rect.y0 - seg.c) < EPS and st.rect.x0 < seg.a1 - EPS
           and seg.a0 < st.rect.x1 - EPS for seg in g.segments()):
        s += 1.0                                        # keep the front for the living room's windows
    axis, c, s0, s1 = st.access("ground")
    mx, my = ((s0 + s1) / 2, c) if axis == "y" else (c, (s0 + s1) / 2)
    s += 0.6 * math.hypot(mx - bb.cx, my - bb.y0) / ext             # near the front door
    tb = fps[-1].bbox()
    s += 0.6 * math.hypot(st.rect.cx - tb.cx, st.rect.cy - tb.cy) / ext   # near the middle: short corridors upstairs
    t = TYPES[st.type]
    return s + 0.3 * t.clear_w * t.clear_l / 1e5


def candidates(fps, stair_type="Auto", walls=None):
    """([Stair] best first, [notes]) for a house of len(fps) >= 2 floors (fps[-1] is the top floor, inside every other);
    `walls` the plan's ExteriorWall / InteriorWall (layout.WALLS when not given)."""
    walls = dict(L.WALLS, **(walls or {}))
    n = len(fps)
    notes = []
    allowed = [t for t in ORDER if TYPES[t].max_floors >= n]
    if stair_type and stair_type != "Auto":
        if stair_type in allowed:
            allowed = [stair_type]
        elif stair_type in TYPES:
            notes.append("StairType %s serves at most %d floors: Auto used" % (stair_type, TYPES[stair_type].max_floors))
        else:
            notes.append("StairType %s unknown: Auto used" % stair_type)
    top = fps[-1]
    used = roles(n)
    found = {}
    for seg in top.segments():
        side = _wall_side(seg)
        for kind in allowed:
            w, l = TYPES[kind].clear_w, TYPES[kind].clear_l
            open_sides = {opening(kind, r)[0] for r in used}
            for o in range(4):
                which = next(k for k, hs in SIDES[o].items() if hs == side)
                if which in open_sides:
                    continue
                dx, dy = (w, l) if o in (0, 2) else (l, w)
                for place in ("start", "end", "middle"):
                    r = _room_rect(seg, side, dx, dy, place, walls)
                    if r is None:
                        continue
                    wall = Stair(kind, r, r, o, n).side_line(which)
                    lo, hi = (r.x0, r.x1) if wall[0] == "y" else (r.y0, r.y1)
                    if not _outside_everywhere(fps, wall[0], wall[1], lo, hi, wall[2]):
                        continue
                    clear = _clear(r, fps, walls)
                    if clear.w < dx - EPS or clear.h < dy - EPS:
                        continue
                    st = Stair(kind, r, clear, o, n)
                    if not st.cells(top.grid) <= top.cells:
                        continue
                    ok = True
                    for k, role in enumerate(used):
                        axis, c, s0, s1 = st.access(role)
                        if L.exterior_parts(fps[k], axis, c, s0, s1, st.access_outward(role)):
                            ok = False
                            break
                    # every floor's rest must still cut into blocks a room can use (spec §6.2)
                    if ok and all(FP.pieces_options(fp, r) for fp in fps):
                        found[(kind, o, round(r.x0, 3), round(r.y0, 3), round(r.x1, 3), round(r.y1, 3))] = st
    ranked = sorted(found.values(), key=lambda st: (round(_score(st, fps), 9), ORDER.index(st.type), st.orient,
                                                     st.rect.x0, st.rect.y0))
    return ranked, notes


# ---------------------------------------------------------------- parts

def _block(st, u0, v0, u1, v1):
    """The stair-frame rectangle u0..u1 x v0..v1 in the house's local frame."""
    (x0, y0), (x1, y1) = st.to_local(u0, v0), st.to_local(u1, v1)
    return Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def flights(st, H):
    """([(role, rect, z0, z1)], [(p0, p1)]): the blocks climbing from a floor to the next H above -- treads ("tread") and
    landings ("landing"), z from the floor -- and the handrails (local points with z), RAIL_UP above the line of the
    nosings. ceil(H / RISE_MAX) risers; a flight's last riser lands on the landing or the floor above, so a floor has
    one block per riser height below the next floor."""
    n = int(math.ceil(H / RISE_MAX - 1e-9))
    r = H / n
    W, Lc = st.dims
    blocks, rails = [], []

    def tread(k, u0, v0, u1, v1):
        blocks.append(("tread", _block(st, u0, v0, u1, v1), k * r - r - UNDER, k * r))

    def rail(u0, v0, z0, u1, v1, z1):
        (x0, y0), (x1, y1) = st.to_local(u0, v0), st.to_local(u1, v1)
        rails.append(((x0, y0, z0 + RAIL_UP), (x1, y1, z1 + RAIL_UP)))

    if st.type == "Straight":
        d = Lc / (n - 1)
        m = 0.5 * (W - FLIGHT_W)
        for k in range(1, n):
            tread(k, (k - 1) * d, m, k * d, m + FLIGHT_W)
        rail(0.0, W - 3.0, r, Lc, W - 3.0, n * r)
        return blocks, rails
    up = (n + 1) // 2                        # the first flight's risers (9 of 17), its last onto the landing
    run = (up - 1) * TREAD
    rest = n - up - 1                        # the second flight's treads
    if st.type == "U":
        m = 0.5 * (W - 2 * FLIGHT_W - GAP)
        va, vb = (m, m + FLIGHT_W), (W - m - FLIGHT_W, W - m)
        for k in range(1, up):
            tread(k, (k - 1) * TREAD, va[0], k * TREAD, va[1])
        blocks.append(("landing", _block(st, run, 0.0, Lc, W), up * r - LANDING_T, up * r))
        d = run / rest
        for j in range(1, rest + 1):
            tread(up + j, run - j * d, vb[0], run - (j - 1) * d, vb[1])
        rail(0.0, va[1] + 2.0, r, run, va[1] + 2.0, up * r)
        rail(run, vb[0] - 2.0, (up + 1) * r, 0.0, vb[0] - 2.0, n * r)
        return blocks, rails
    # L: flight A along u on v 0..FLIGHT_W, the corner landing at the far end, flight B along +v to the v = W side
    for k in range(1, up):
        tread(k, (k - 1) * TREAD, 0.0, k * TREAD, FLIGHT_W)
    blocks.append(("landing", _block(st, run, 0.0, Lc, FLIGHT_W), up * r - LANDING_T, up * r))
    d = (W - FLIGHT_W) / rest
    for j in range(1, rest + 1):
        tread(up + j, Lc - FLIGHT_W, FLIGHT_W + (j - 1) * d, Lc, FLIGHT_W + j * d)
    rail(0.0, FLIGHT_W + 2.0, r, run, FLIGHT_W + 2.0, up * r)
    rail(Lc - FLIGHT_W - 2.0, FLIGHT_W, (up + 1) * r, Lc - FLIGHT_W - 2.0, W, n * r)
    return blocks, rails


def parts(st, out, level, shown_above, top_shown, H, pal):
    """The stair's parts on floor `level`, in `out` (that floor's frame): the flights up to the next floor -- on the top
    floor shown when the next one is not (the cutaway view), only as high as its walls, without handrails -- and on the
    U's top floor the guard rail along the open half of its opening (over the flight below)."""
    if level < st.n_floors - 1:
        blocks, rails = flights(st, H)
        clip = top_shown and not shown_above and out.top is not None
        for role, rect, z0, z1 in blocks:
            if level == 0:
                z0 = max(z0, 0.0)                         # on the ground floor the first treads stand on the floor
            if clip:
                if z0 >= out.top - EPS:
                    continue
                z1 = min(z1, out.top)
            out.box(rect, z0, z1, pal["wood"], role)
        if not clip:
            for p0, p1 in rails:
                out.bar(p0, p1, HAND_T, pal["wood_dark"], "handrail")
    role = st.role(level)
    void = st.void(role)
    if void is not None:
        axis, c, s0, s1 = void
        T.railing(out, axis, c, s0, s1, -st.access_outward(role), pal)
