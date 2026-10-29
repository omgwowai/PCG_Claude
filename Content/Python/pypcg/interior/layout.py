"""PyInterior layout (spec 2026-10-28 §4.4): the zoning grammar that cuts a footprint into rectangular rooms.

    House   -> [Public | Private]          along a wing's axis (one wing), or wing by wing (L / T / U)
    Public  -> one, two or three public rooms: front / back, side by side, in a row
    Private -> Column  [Room]*              rooms along the zone border, each entered from the public zone
             | Gallery [Corridor | Row]    a corridor along the zone border, one row of rooms behind it
             | Single  [Corridor | Row]    a corridor from the border with one row of rooms beside it
             | Double  [Row | Corridor | Row]
               (Single / Double optionally with an end room across the corridor's far end)
    Row     -> [Room]*                     sized by target area, each at least its minimum, a Storage filler where the rooms
                                           alone would get too long

Every candidate is checked whole -- minimum clear sizes, an exterior wall for every habitable room, every room reachable from
the front door through an allowed passage (program.ACCESS) -- and scored (area error, aspect, circulation); the best valid
one wins and the seed picks among near-ties. A program that fits nowhere drops its optional rooms, then steps down a program
(program.fallbacks). Pure."""
import itertools
import math
from dataclasses import dataclass, field

from pypcg.interior import program as P
from pypcg.interior.footprint import EPS, Rect

SNAP = 10.0                  # partition lines on 10 cm
CORRIDOR = 130.0             # corridor width on the partition (118 clear between interior walls, 99 along an exterior one)
ALLOW = 31.0                 # wall allowance per dimension while sizing (an exterior 25 + half an interior 12)
WALLS = {"ext": 25.0, "int": 12.0, "height": 270.0}
SPAN = {"door": 120.0, "bath": 110.0, "doorway": 110.0, "opening": 120.0}   # shared wall a passage needs
FRONT_MIN = 120.0            # the front door needs this much exterior front wall on the entry room
WINDOW_CORNER = 40.0         # a window keeps this far from the clear corners of its room
WINDOW_MIN = 90.0            # a habitable room needs this much window-able exterior wall
HABITABLE = ("Main", "Living", "Master", "Bedroom")
MAX_ASPECT = {"Main": 2.0, "Living": 2.0, "Kitchen": 2.8, "Dining": 1.8, "Master": 1.7, "Bedroom": 1.8, "Study": 2.0,
              "Bath": 1.6, "WC": 2.2, "Laundry": 2.0, "Storage": 3.5, "Corridor": 99.0}
TOP_K = 4                    # candidates kept per block before they are combined
ACCESS_COST = 0.15           # per step down a room's ACCESS preference list (a bedroom off the dining room: 2 steps)
NEAR = 0.03                  # scores within 3 % of the best are a tie, the seed picks
NO_FIT = "no program fits the footprint"


def snap(v):
    return round(v / SNAP) * SNAP


def snap_up(v):
    return math.ceil(v / SNAP - 1e-9) * SNAP


@dataclass
class Room:
    id: int
    type: str
    rect: Rect
    block: int = 0

    @property
    def zone(self):
        return P.ROOMS[self.type].zone


@dataclass
class Plan:
    footprint: object
    program: object
    rooms: list
    front_room: int
    entry: tuple                  # (x0, x1, y): the exterior stretch of the front room's front side
    walls: dict
    failures: list
    parents: dict = field(default_factory=dict)
    score: float = 0.0

    def room(self, rid):
        return next(r for r in self.rooms if r.id == rid)


# ---------------------------------------------------------------- the footprint's outside

def exterior_parts(fp, axis, c, a0, a1, outward):
    """The stretches of the side (axis, c, a0..a1) whose outside (towards `outward`) is not in the footprint."""
    g = fp.grid
    k = c / g
    if abs(k - round(k)) > 1e-6:
        return []
    k = int(round(k))
    o = k if outward > 0 else k - 1
    parts = []
    for m in range(int(math.floor(a0 / g + 1e-9)), int(math.ceil(a1 / g - 1e-9))):
        if ((o, m) if axis == "x" else (m, o)) in fp.cells:
            continue
        lo, hi = max(a0, m * g), min(a1, (m + 1) * g)
        if hi - lo <= EPS:
            continue
        if parts and abs(parts[-1][1] - lo) < EPS:
            parts[-1] = (parts[-1][0], hi)
        else:
            parts.append((lo, hi))
    return parts


def exterior_length(rect, fp):
    return sum(b - a for axis, c, a0, a1, out in rect.edges() for a, b in exterior_parts(fp, axis, c, a0, a1, out))


def window_parts(rect, fp, walls=WALLS):
    """[(axis, c, outward, lo, hi)]: the exterior stretches of the room's sides where a window may go -- inside the
    room's clear width and WINDOW_CORNER from its corners."""
    cr = None
    out = []
    for axis, c, a0, a1, outward in rect.edges():
        parts = exterior_parts(fp, axis, c, a0, a1, outward)
        if not parts:
            continue
        cr = cr or clear_rect(rect, fp, walls)
        clo, chi = (cr.y0, cr.y1) if axis == "x" else (cr.x0, cr.x1)
        for lo, hi in parts:
            lo, hi = max(lo, clo) + WINDOW_CORNER, min(hi, chi) - WINDOW_CORNER
            if hi - lo > EPS:
                out.append((axis, c, outward, lo, hi))
    return out


def window_length(rect, fp, walls=WALLS):
    return max((hi - lo for _a, _c, _o, lo, hi in window_parts(rect, fp, walls)), default=0.0)


def clear_rect(rect, fp, walls=WALLS):
    """The room's floor inside its walls: an exterior wall's full thickness, half an interior wall's."""
    ins = [walls["ext"] if exterior_parts(fp, axis, c, a0, a1, out) else 0.5 * walls["int"]
           for axis, c, a0, a1, out in rect.edges()]
    b, r, t, l = ins
    return rect.shrink(l, b, r, t)


def front_part(rect, fp):
    parts = exterior_parts(fp, "y", rect.y0, rect.x0, rect.x1, -1)
    return max(parts, key=lambda p: (p[1] - p[0], -p[0])) if parts else None


# ---------------------------------------------------------------- passages

def passage(parent, child):
    if frozenset((parent, child)) in P.OPEN:
        return "opening"
    if child in P.DOORWAY:
        return "doorway"
    if child in ("Bath", "WC", "Laundry", "Storage"):
        return "bath"
    return "door"


def shared_length(a, b):
    s = a.shared(b)
    return s[3] - s[2] if s else 0.0


TIER = {"Kitchen": 0, "Dining": 0, "Corridor": 0}


def connect(rooms, fp, front_room):
    """{room id: parent id} reaching every room from the front room, each through the first already-reached neighbour of
    an allowed type (program.ACCESS order) that shares enough wall for the passage; None when a room cannot be reached.
    Corridors and the public rooms are resolved before the rooms that hang off them."""
    parents = {front_room: None}
    for tier in (0, 1):
        changed = True
        while changed:
            changed = False
            for r in rooms:
                if r.id in parents or TIER.get(r.type, 1) != tier:
                    continue
                for ptype in P.ACCESS.get(r.type, ()):
                    need = SPAN[passage(ptype, r.type)]
                    cands = [q for q in rooms if q.id in parents and q.type == ptype
                             and shared_length(q.rect, r.rect) >= need - EPS]
                    if cands:
                        parents[r.id] = max(cands, key=lambda q: (shared_length(q.rect, r.rect), -q.id)).id
                        changed = True
                        break
    return parents if len(parents) == len(rooms) else None


# ---------------------------------------------------------------- rows

def min_width(t, depth):
    """The least width (wall allowance included) a room of type t needs at this depth, or None if the depth is too small."""
    rt = P.ROOMS[t]
    d = depth - ALLOW
    if d >= rt.min_long - EPS:
        w = rt.min_short
    elif d >= rt.min_short - EPS:
        w = rt.min_long
    else:
        return None
    return snap_up(w + ALLOW)


def max_width(t, depth):
    return MAX_ASPECT[t] * max(depth - ALLOW, 1.0) + ALLOW


def split_row(length, depth, types, targets, filler_first=False):
    """[(type, width)] filling `length` exactly: widths in proportion to the target areas above each room's minimum,
    snapped to 10 cm; a Storage filler takes what the rooms cannot use without getting too long. None if they do not fit."""
    types, targets = list(types), list(targets)
    mins = [min_width(t, depth) for t in types]
    if any(m is None for m in mins):
        return None
    cap = sum(max(max_width(t, depth), m) for t, m in zip(types, mins))
    fmin = min_width("Storage", depth)
    if fmin is not None and length - cap >= fmin - EPS:
        fw = snap(length - cap)
        if filler_first:
            types, targets, mins = ["Storage"] + types, [fw * depth] + targets, [fmin] + mins
        else:
            types, targets, mins = types + ["Storage"], targets + [fw * depth], mins + [fmin]
    if sum(mins) > length + EPS:
        return None
    ideal = [max(m, a / depth) for m, a in zip(mins, targets)]
    extra = [i - m for i, m in zip(ideal, mins)]
    free, tot = length - sum(mins), sum(extra)
    ws = [m + (free * e / tot if tot > EPS else free / len(mins)) for m, e in zip(mins, extra)]
    out, acc = [], 0.0
    for k, (t, w, m) in enumerate(zip(types, ws, mins)):
        w = length - acc if k == len(ws) - 1 else max(snap(w), m)
        if w < m - EPS:
            return None
        out.append((t, w))
        acc += w
    return out


# ---------------------------------------------------------------- block coordinates

class Side:
    """A block seen from one of its sides: u runs from that side into the block, v along it."""

    def __init__(self, rect, side):
        self.B, self.side = rect, side
        self.U = rect.w if side in ("left", "right") else rect.h
        self.V = rect.h if side in ("left", "right") else rect.w

    def rect(self, u0, v0, u1, v1):
        B = self.B
        if self.side == "left":
            return Rect(B.x0 + u0, B.y0 + v0, B.x0 + u1, B.y0 + v1)
        if self.side == "right":
            return Rect(B.x1 - u1, B.y0 + v0, B.x1 - u0, B.y0 + v1)
        if self.side == "bottom":
            return Rect(B.x0 + v0, B.y0 + u0, B.x0 + v1, B.y0 + u1)
        return Rect(B.x0 + v0, B.y1 - u1, B.x0 + v1, B.y1 - u0)

    def v_of(self, a):
        return a - (self.B.y0 if self.side in ("left", "right") else self.B.x0)


def side_of(rect, shared):
    axis, c = shared[0], shared[1]
    if axis == "x":
        return "left" if abs(c - rect.x0) < EPS else "right"
    return "bottom" if abs(c - rect.y0) < EPS else "top"


def _valid_rect(r):
    return r.w > EPS and r.h > EPS


# ---------------------------------------------------------------- public zone

def _fracs(f, lo=0.2, hi=0.8):
    return sorted({round(min(hi, max(lo, f * k)), 4) for k in (0.85, 1.0, 1.15)})


def public_layouts(B, slots):
    types = [s.type for s in slots]
    w = [s.weight for s in slots]
    tot = sum(w)
    if len(types) == 1:
        return [[(types[0], B)]]
    out = []
    if len(types) == 2:
        a, b = types
        for f in _fracs(w[0] / tot):
            y = snap(B.y0 + B.h * f)
            out.append([(a, Rect(B.x0, B.y0, B.x1, y)), (b, Rect(B.x0, y, B.x1, B.y1))])
            x = snap(B.x0 + B.w * f)
            out.append([(a, Rect(B.x0, B.y0, x, B.y1)), (b, Rect(x, B.y0, B.x1, B.y1))])
            x = snap(B.x1 - B.w * f)
            out.append([(a, Rect(x, B.y0, B.x1, B.y1)), (b, Rect(B.x0, B.y0, x, B.y1))])
    else:
        live, kit, din = types[0], types[1], types[2]
        fl = w[0] / tot
        for f in _fracs(fl):
            y = snap(B.y0 + B.h * f)
            for g in _fracs(w[1] / (w[1] + w[2]), 0.3, 0.7):
                x = snap(B.x0 + B.w * g)
                out.append([(live, Rect(B.x0, B.y0, B.x1, y)), (kit, Rect(B.x0, y, x, B.y1)), (din, Rect(x, y, B.x1, B.y1))])
                x = snap(B.x1 - B.w * g)
                out.append([(live, Rect(B.x0, B.y0, B.x1, y)), (kit, Rect(x, y, B.x1, B.y1)), (din, Rect(B.x0, y, x, B.y1))])
            for left in (True, False):
                x = snap(B.x0 + B.w * f) if left else snap(B.x1 - B.w * f)
                lv = Rect(B.x0, B.y0, x, B.y1) if left else Rect(x, B.y0, B.x1, B.y1)
                ox0, ox1 = (x, B.x1) if left else (B.x0, x)
                for g in _fracs(w[2] / (w[1] + w[2]), 0.3, 0.7):
                    y2 = snap(B.y0 + B.h * g)
                    out.append([(live, lv), (din, Rect(ox0, B.y0, ox1, y2)), (kit, Rect(ox0, y2, ox1, B.y1))])
        fs = (w[0] / tot, w[2] / tot)
        x1 = snap(B.x0 + B.w * fs[0])
        x2 = snap(x1 + B.w * fs[1])
        out.append([(live, Rect(B.x0, B.y0, x1, B.y1)), (din, Rect(x1, B.y0, x2, B.y1)), (kit, Rect(x2, B.y0, B.x1, B.y1))])
        x1 = snap(B.x1 - B.w * fs[0])
        x2 = snap(x1 - B.w * fs[1])
        out.append([(live, Rect(x1, B.y0, B.x1, B.y1)), (din, Rect(x2, B.y0, x1, B.y1)), (kit, Rect(B.x0, B.y0, x2, B.y1))])
        y1 = snap(B.y0 + B.h * fs[0])
        y2 = snap(y1 + B.h * fs[1])
        out.append([(live, Rect(B.x0, B.y0, B.x1, y1)), (din, Rect(B.x0, y1, B.x1, y2)), (kit, Rect(B.x0, y2, B.x1, B.y1))])
    return [c for c in out if all(_valid_rect(r) for _t, r in c)]


# ---------------------------------------------------------------- private zone

WET = ("Bath", "WC", "Laundry")


def _orders(idx, types):
    if len(idx) <= 4:
        return list(dict.fromkeys(itertools.permutations(idx)))
    wet = [i for i in idx if types[i] in WET]
    dry = [i for i in idx if types[i] not in WET]
    outs = [tuple(idx), tuple(wet + dry), tuple(dry + wet), tuple(dry[:1] + wet + dry[1:]),
            tuple(dry[:2] + wet + dry[2:]), tuple(reversed(idx))]
    return list(dict.fromkeys(outs))


def _row_rooms(S, row, u0, ulen_axis, v0, v1, along="u"):
    """Rooms of a split row: along u from u0 (in the band v0..v1) or along v from v0 (in the band u0..ulen_axis)."""
    out, acc = [], 0.0
    for t, w in row:
        if along == "u":
            out.append((t, S.rect(u0 + acc, v0, u0 + acc + w, v1)))
        else:
            out.append((t, S.rect(u0, v0 + acc, ulen_axis, v0 + acc + w)))
        acc += w
    return out


def _end_choices(idx, types, tg, S):
    out = [None]
    pick = [i for i in idx if types[i] == "Master"] or sorted(idx, key=lambda i: -tg[i])[:1]
    for i in pick:
        m = min_width(types[i], S.V)
        if m is None:
            continue
        e = max(m, snap(tg[i] / S.V))
        if S.U - e >= 200.0:
            out.append((i, e))
    return out


def _two_rows(rest, types, tg):
    """A few ways to share the rooms between the two rows of a double-loaded corridor."""
    by = sorted(rest, key=lambda i: -tg[i])
    outs = []
    a, b, sa, sb = [], [], 0.0, 0.0
    for i in by:
        if sa <= sb:
            a.append(i)
            sa += tg[i]
        else:
            b.append(i)
            sb += tg[i]
    outs.append((a, b))
    half = (len(rest) + 1) // 2
    outs.append((list(rest[:half]), list(rest[half:])))
    wet = [i for i in rest if types[i] in WET]
    dry = [i for i in rest if types[i] not in WET]
    if wet and dry:
        h = (len(dry) + 1) // 2
        outs.append((dry[:h], wet + dry[h:]))
        outs.append((wet + dry[:h], dry[h:]))
    seen, res = set(), []
    for a, b in outs:
        if a and b:
            key = (tuple(a), tuple(b))
            if key not in seen:
                seen.add(key)
                res.append((a, b))
    return res


def private_layouts(B, slots, side, span):
    """Candidate room sets for a private block entered over `span` (v0, v1) of its `side`."""
    S = Side(B, side)
    U, V = S.U, S.V
    sv0, sv1 = span
    types = [s.type for s in slots]
    tg = P.targets(slots, B.area)
    idx = list(range(len(slots)))
    out = []
    # Column: rooms along v, each from the border (u = 0) to the far side
    for order in _orders(idx, types):
        for ff in (False, True):
            row = split_row(V, U, [types[i] for i in order], [tg[i] for i in order], ff)
            if row:
                out.append(_row_rooms(S, row, 0.0, U, 0.0, V, along="v"))
    # Chain: rooms one behind the other from the border -- a bedroom with its own bathroom behind it in a shallow house
    for order in _orders(idx, types):
        row = split_row(U, V, [types[i] for i in order], [tg[i] for i in order])
        if row:
            out.append(_row_rooms(S, row, 0.0, None, 0.0, V, along="u"))
    # Gallery: the corridor along the border (u in [0, C]), one row of rooms behind it -- for a shallow, wide zone
    if U - CORRIDOR > EPS and sv1 - sv0 >= SPAN["doorway"] - EPS:
        for order in _orders(idx, types):
            for ff in (False, True):
                row = split_row(V, U - CORRIDOR, [types[i] for i in order], [tg[i] for i in order], ff)
                if row:
                    out.append([("Corridor", S.rect(0.0, 0.0, CORRIDOR, V))] +
                               _row_rooms(S, row, CORRIDOR, U, 0.0, V, along="v"))
    # Single: the corridor along u at one edge of the block (inside the border span), one row beside it
    for cv in sorted({sv0, sv1 - CORRIDOR}):
        if cv < sv0 - EPS or cv + CORRIDOR > sv1 + EPS:
            continue
        if cv > EPS and V - (cv + CORRIDOR) > EPS:
            continue
        rv0, rv1 = (CORRIDOR, V) if cv <= EPS else (0.0, V - CORRIDOR)
        for end in _end_choices(idx, types, tg, S):
            ulen = U - (end[1] if end else 0.0)
            rest = [i for i in idx if not end or i != end[0]]
            if not rest:
                continue
            for order in _orders(rest, types):
                for ff in (False, True):
                    row = split_row(ulen, rv1 - rv0, [types[i] for i in order], [tg[i] for i in order], ff)
                    if not row:
                        continue
                    rooms = [("Corridor", S.rect(0.0, cv, ulen, cv + CORRIDOR))]
                    rooms += _row_rooms(S, row, 0.0, None, rv0, rv1, along="u")
                    if end:
                        rooms.append((types[end[0]], S.rect(ulen, 0.0, U, V)))
                    out.append(rooms)
    # Double: a corridor between two rows
    for end in _end_choices(idx, types, tg, S):
        ulen = U - (end[1] if end else 0.0)
        rest = [i for i in idx if not end or i != end[0]]
        if len(rest) < 2:
            continue
        for ra, rb in _two_rows(rest, types, tg):
            area_a, area_b = sum(tg[i] for i in ra), sum(tg[i] for i in rb)
            a0 = snap((V - CORRIDOR) * area_a / (area_a + area_b))
            for a in sorted({a0 - 30.0, a0, a0 + 30.0}):
                if a < sv0 - EPS or a + CORRIDOR > sv1 + EPS or a <= EPS or V - a - CORRIDOR <= EPS:
                    continue
                for oa in _orders(ra, types)[:4]:
                    rowa = split_row(ulen, a, [types[i] for i in oa], [tg[i] for i in oa])
                    if not rowa:
                        continue
                    for ob in _orders(rb, types)[:4]:
                        rowb = split_row(ulen, V - a - CORRIDOR, [types[i] for i in ob], [tg[i] for i in ob])
                        if not rowb:
                            continue
                        rooms = [("Corridor", S.rect(0.0, a, ulen, a + CORRIDOR))]
                        rooms += _row_rooms(S, rowa, 0.0, None, 0.0, a, along="u")
                        rooms += _row_rooms(S, rowb, 0.0, None, a + CORRIDOR, V, along="u")
                        if end:
                            rooms.append((types[end[0]], S.rect(ulen, 0.0, U, V)))
                        out.append(rooms)
    return [c for c in out if all(_valid_rect(r) for _t, r in c)]


# ---------------------------------------------------------------- checks and scores

def _sizes_ok(rooms, fp, walls):
    for t, r in rooms:
        rt = P.ROOMS[t]
        c = clear_rect(r, fp, walls)
        if c.short < rt.min_short - EPS or c.long < rt.min_long - EPS:
            return False
        if t in HABITABLE and window_length(r, fp, walls) < WINDOW_MIN - EPS:
            return False
    return True


def _score(rooms, fp, walls, targets):
    s = 0.0
    for (t, r), tgt in zip(rooms, targets):
        c = clear_rect(r, fp, walls)
        aspect = c.long / max(c.short, 1.0)
        if t in ("Corridor", "Storage"):
            s += 2.0 * r.area / fp.area
            continue
        if tgt:
            s += ((r.area - tgt) / tgt) ** 2
        s += 4.0 * max(0.0, aspect - MAX_ASPECT[t]) ** 2 + 0.05 * (aspect - 1.0)
    return s


def _local_connect(rooms, fp, entry_rect, entry_type):
    tmp = [Room(k, t, r) for k, (t, r) in enumerate(rooms)]
    tmp.append(Room(len(tmp), entry_type, entry_rect))
    return connect(tmp, fp, len(tmp) - 1) is not None


def _entry_strip(B, side, span):
    v0, v1 = span
    S = Side(B, side)
    a, b = S.rect(0.0, v0, 1.0, v1), None
    if side == "left":
        b = Rect(B.x0 - 10.0, a.y0, B.x0, a.y1)
    elif side == "right":
        b = Rect(B.x1, a.y0, B.x1 + 10.0, a.y1)
    elif side == "bottom":
        b = Rect(a.x0, B.y0 - 10.0, a.x1, B.y0)
    else:
        b = Rect(a.x0, B.y1, a.x1, B.y1 + 10.0)
    return b


# ---------------------------------------------------------------- blocks

def _pub_share(prog):
    wp = sum(s.weight for s in prog.public)
    wq = sum(s.weight for s in prog.private)
    return wp / (wp + wq) if wp + wq else 1.0


def _front_len(fp, w):
    return sum(b - a for a, b in exterior_parts(fp, "y", w.y0, w.x0, w.x1, -1))


def configs(fp, prog, mirror=False):
    """Ways to cut the footprint into one public block and entered private blocks:
    [(public rect, [(private rect, side, span)])]."""
    share = _pub_share(prog)
    out = []
    if len(fp.wings) == 1:
        W = fp.wings[0]
        if not prog.private:
            return [(W, [])]
        for f in sorted({round(min(0.85, max(0.2, share * k)), 4) for k in (0.8, 0.9, 1.0, 1.1, 1.2, 1.35)}):
            for left in ((False, True) if mirror else (True, False)):
                x = snap(W.x0 + W.w * f) if left else snap(W.x1 - W.w * f)
                if left:
                    pub, priv, side = Rect(W.x0, W.y0, x, W.y1), Rect(x, W.y0, W.x1, W.y1), "left"
                else:
                    pub, priv, side = Rect(x, W.y0, W.x1, W.y1), Rect(W.x0, W.y0, x, W.y1), "right"
                if _valid_rect(pub) and _valid_rect(priv):
                    out.append((pub, [(priv, side, (0.0, priv.h))]))
            y = snap(W.y0 + W.h * f)
            pub, priv = Rect(W.x0, W.y0, W.x1, y), Rect(W.x0, y, W.x1, W.y1)
            if _valid_rect(pub) and _valid_rect(priv):
                out.append((pub, [(priv, "bottom", (0.0, priv.w))]))
        return out
    entry = max(fp.wings, key=lambda w: (_front_len(fp, w), w.area, -w.x0))
    others = [w for w in fp.wings if w != entry]
    ideal = fp.area * share
    splits = [None]
    if prog.private and entry.area > 1.25 * ideal:
        splits += [ideal * k for k in (0.9, 1.0, 1.15)]
    for target in splits:
        blocks = []
        if target is None:
            pub = entry
        elif entry.w >= entry.h:
            # the public part at the end away from the other wings
            cx = sum((s[2] + s[3]) / 2 for o in others for s in [entry.shared(o)] if s and s[0] == "y") or None
            far_left = cx is not None and cx / max(1, len([1 for o in others if (entry.shared(o) or "z")[0] == "y"])) > entry.cx
            p = snap(min(0.8 * entry.w, max(0.35 * entry.w, target / entry.h)))
            if far_left:
                pub, rest = Rect(entry.x0, entry.y0, entry.x0 + p, entry.y1), Rect(entry.x0 + p, entry.y0, entry.x1, entry.y1)
            else:
                pub, rest = Rect(entry.x1 - p, entry.y0, entry.x1, entry.y1), Rect(entry.x0, entry.y0, entry.x1 - p, entry.y1)
            blocks.append(rest)
        else:
            p = snap(min(0.8 * entry.h, max(0.35 * entry.h, target / entry.w)))
            pub, rest = Rect(entry.x0, entry.y0, entry.x1, entry.y0 + p), Rect(entry.x0, entry.y0 + p, entry.x1, entry.y1)
            blocks.append(rest)
        blocks += others
        # enter every private block from the block it shares the longest edge with, breadth first from the public one
        entered, placed, todo = [pub], [], list(blocks)
        progress = True
        while todo and progress:
            progress = False
            for b in list(todo):
                best = None
                for n in entered:
                    s = b.shared(n)
                    if s and s[3] - s[2] >= 120.0 - EPS and (best is None or s[3] - s[2] > best[3] - best[2]):
                        best = s
                if best is not None:
                    S = Side(b, side_of(b, best))
                    placed.append((b, S.side, (S.v_of(best[2]), S.v_of(best[3]))))
                    entered.append(b)
                    todo.remove(b)
                    progress = True
        if not todo and all(_valid_rect(b) for b, _s, _p in placed) and _valid_rect(pub):
            out.append((pub, placed))
    return out


def distribute(slots, blocks):
    """A few ways to share the private slots between the private blocks (each block gets at least one room; a block the
    program cannot fill gets a Storage room)."""
    n = len(blocks)
    if n == 1:
        return [[list(slots)]]
    areas = [b[0].area for b in blocks]
    outs = []
    for wet_first in (True, False):
        order = sorted(range(len(slots)), key=lambda i: (-(slots[i].type in WET) if wet_first else 0, -slots[i].weight, i))
        groups = [[] for _ in range(n)]
        load = [0.0] * n
        total_w = sum(s.weight for s in slots)
        for i in order:
            s = slots[i]
            if s.type in WET and wet_first:
                k = 0
            else:
                k = min(range(n), key=lambda b: (load[b] / areas[b], -areas[b]))
            groups[k].append(s)
            load[k] += s.weight * sum(areas) / total_w
        for k in range(n):
            if not groups[k]:
                groups[k].append(P.Slot("Storage", 1.0))
        outs.append(groups)
    res, seen = [], set()
    for g in outs:
        key = tuple(tuple((s.type, s.weight) for s in grp) for grp in g)
        if key not in seen:
            seen.add(key)
            res.append(g)
    return res


# ---------------------------------------------------------------- the plan

def _try(fp, prog, rng, walls, mirror):
    best = []
    for pub, privs in configs(fp, prog, mirror):
        pub_c = []
        tg_pub = P.targets(prog.public, pub.area)
        for cand in public_layouts(pub, prog.public):
            if not _sizes_ok(cand, fp, walls):
                continue
            entries = [(t, r) for t, r in cand if t in P.ENTRY]
            if not entries or not front_part(entries[0][1], fp) or \
                    front_part(entries[0][1], fp)[1] - front_part(entries[0][1], fp)[0] < FRONT_MIN - EPS:
                continue
            pub_c.append((_score(cand, fp, walls, tg_pub), cand))
        if not pub_c:
            continue
        pub_c.sort(key=lambda c: c[0])
        pub_c = pub_c[:TOP_K]
        groups_list = distribute(prog.private, privs) if privs else [[]]
        for groups in groups_list:
            per_block = []
            ok = True
            for (b, side, span), grp in zip(privs, groups):
                cands = []
                strip = _entry_strip(b, side, span)
                tg = P.targets(grp, b.area)
                for cand in private_layouts(b, grp, side, span):
                    if not _sizes_ok(cand, fp, walls):
                        continue
                    if not _local_connect(cand, fp, strip, "Living"):
                        continue
                    tmap = []
                    gi = 0
                    for t, _r in cand:
                        if t in ("Corridor", "Storage"):
                            tmap.append(0.0)
                        else:
                            tmap.append(None)
                    # targets by order of the group's rooms (types may repeat)
                    left = list(zip([s.type for s in grp], tg))
                    tl = []
                    for t, _r in cand:
                        hit = next((k for k, (tt, _a) in enumerate(left) if tt == t), None)
                        if hit is None:
                            tl.append(0.0)
                        else:
                            tl.append(left.pop(hit)[1])
                    cands.append((_score(cand, fp, walls, tl), cand))
                if not cands:
                    ok = False
                    break
                cands.sort(key=lambda c: c[0])
                per_block.append(cands[:TOP_K])
            if not ok:
                continue
            for pc in pub_c:
                for combo in itertools.product(*per_block) if per_block else [()]:
                    rooms = list(pc[1]) + [rc for _s, c in combo for rc in c]
                    s = pc[0] + sum(c[0] for c in combo)
                    linked = _link(fp, rooms)
                    if linked is not None:
                        best.append((s + _access_cost(linked[0], linked[1]), rooms))
    if not best:
        return None
    best.sort(key=lambda c: c[0])
    for s, rooms in _near(best, rng):
        plan = _assemble(fp, prog, rooms, walls, s)
        if plan is not None:
            return plan
    return None


def _link(fp, rooms):
    """(Room list, parents) of a candidate, or None when its front room cannot take the front door or a room is
    unreachable."""
    rs = [Room(k, t, r) for k, (t, r) in enumerate(rooms)]
    entries = [r for r in rs if r.type in P.ENTRY]
    if not entries:
        return None
    front = max(entries, key=lambda r: (_part_len(front_part(r.rect, fp)), -r.id))
    if _part_len(front_part(front.rect, fp)) < FRONT_MIN - EPS:
        return None
    parents = connect(rs, fp, front.id)
    return None if parents is None else (rs, parents)


def _part_len(part):
    return part[1] - part[0] if part else 0.0


def _access_cost(rs, parents):
    by = {r.id: r for r in rs}
    cost = 0.0
    for rid, pid in parents.items():
        if pid is not None:
            prefs = P.ACCESS.get(by[rid].type, ())
            t = by[pid].type
            cost += ACCESS_COST * (prefs.index(t) if t in prefs else len(prefs))
    return cost


def _near(best, rng):
    """The candidates in the order to try: the near-ties of the best in seed order first, then the rest by score."""
    top = best[0][0]
    tie = [c for c in best if c[0] <= top * (1.0 + NEAR) + 1e-9]
    rest = [c for c in best if c[0] > top * (1.0 + NEAR) + 1e-9]
    rng.shuffle(tie)
    return tie + rest


def _assemble(fp, prog, rooms, walls, score):
    rs = [Room(k, t, r) for k, (t, r) in enumerate(rooms)]
    entries = [r for r in rs if r.type in P.ENTRY]
    if not entries:
        return None
    front = max(entries, key=lambda r: ((front_part(r.rect, fp) or (0, 0))[1] - (front_part(r.rect, fp) or (0, 0))[0], -r.id))
    fpart = front_part(front.rect, fp)
    if not fpart or fpart[1] - fpart[0] < FRONT_MIN - EPS:
        return None
    parents = connect(rs, fp, front.id)
    if parents is None:
        return None
    _master_is_largest(rs, fp, walls)
    return Plan(fp, prog, rs, front.id, (fpart[0], fpart[1], front.rect.y0), dict(walls), [], parents, score)


def _master_is_largest(rs, fp, walls):
    """The program's rooms go to blocks by area, so the master can land in a small block: give the name to the largest
    bedroom that meets the master's minimum."""
    master = next((r for r in rs if r.type == "Master"), None)
    if master is None:
        return
    mt = P.ROOMS["Master"]
    fits = [r for r in rs if r.type in ("Master", "Bedroom") and clear_rect(r.rect, fp, walls).short >= mt.min_short - EPS
            and clear_rect(r.rect, fp, walls).long >= mt.min_long - EPS]
    if fits:
        big = max(fits, key=lambda r: (clear_rect(r.rect, fp, walls).w * clear_rect(r.rect, fp, walls).h, -r.id))
        if big is not master:
            master.type, big.type = "Bedroom", "Master"


def plan(fp, program, rng, walls=None, mirror=False, skip=()):
    """The house's rooms: the first program in program.fallbacks(program) that has a valid layout, its best layout;
    `skip`: variants not to use (pypcg.interior.house: their required furniture did not fit)."""
    walls = dict(WALLS, **(walls or {}))
    for prog in P.fallbacks(program):
        if prog in skip:
            continue
        p = _try(fp, prog, rng, walls, mirror)
        if p is not None:
            return p
    # nothing fits: one open room per wing, reported
    rooms = [Room(k, "Main", w) for k, w in enumerate(fp.wings)]
    fpart = front_part(rooms[0].rect, fp) or (rooms[0].rect.x0, rooms[0].rect.x1)
    return Plan(fp, P.PROGRAMS[0], rooms, 0, (fpart[0], fpart[1], rooms[0].rect.y0), dict(walls), [NO_FIT], {0: None})
