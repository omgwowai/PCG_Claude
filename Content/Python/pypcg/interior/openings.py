"""PyInterior windows (spec 2026-10-28 §4.6): every exterior stretch of a room's walls gets the wall grammar [S][W,S]* --
W a window of the room type's width (fixed), S plain wall (scalable): the solver picks the window count whose wall pieces
need the scale closest to 1, so a longer wall gets more windows. Windows keep layout.WINDOW_CORNER from the room's corners
and DOOR_CLEAR from a door on the same wall; a stretch too short for the grammar still takes one narrower window
(down to NARROW of the width). Pure."""
import random
from dataclasses import dataclass

from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.interior.footprint import EPS
from pypcg.world import grammar as G

WINDOWS = {     # kind: (width, sill, height, plain wall between windows), cm
    "living": (160.0, 50.0, 170.0, 110.0),
    "dining": (140.0, 70.0, 150.0, 100.0),
    "bedroom": (120.0, 90.0, 130.0, 100.0),
    "kitchen": (100.0, 105.0, 110.0, 80.0),
    "high": (60.0, 150.0, 60.0, 80.0),
}
DOOR_CLEAR = 40.0
NARROW = 0.6
GRAMMAR = G.parse("[S][W,S]*")


@dataclass(frozen=True)
class Window:
    room: int
    axis: str                # "x": on the wall line x = c; "y": on y = c
    c: float
    s0: float
    s1: float
    sill: float
    height: float
    kind: str
    outward: int             # the outside lies on this side of the wall line (-1 / +1 across it)

    @property
    def width(self):
        return self.s1 - self.s0


def _minus(lo, hi, cuts):
    """[lo, hi] without the intervals `cuts`."""
    out = [(lo, hi)]
    for a, b in sorted(cuts):
        nxt = []
        for x, y in out:
            if b <= x or a >= y:
                nxt.append((x, y))
                continue
            if a > x:
                nxt.append((x, a))
            if b < y:
                nxt.append((b, y))
        out = nxt
    return [(x, y) for x, y in out if y - x > EPS]


def fill(lo, hi, kind, rng):
    """[(s0, s1)] of the windows the grammar puts on the wall stretch lo..hi."""
    w, _sill, _h, solid = WINDOWS[kind]
    length = hi - lo
    if length < NARROW * w - EPS:
        return []
    res = G.solve(GRAMMAR, length, {"S": solid, "W": w}, {"S"}, rng, smin=0.35, smax=6.0)
    spots = [(lo + a, lo + b) for sym, (a, b) in zip(res["symbols"], G.positions(res, {"S": solid, "W": w}, {"S"}))
             if sym == "W"]
    if spots and res["ok"]:
        return spots
    ww = min(w, length)
    m = 0.5 * (lo + hi)
    return [(m - 0.5 * ww, m + 0.5 * ww)]


def windows(plan, doors, rng=None):
    rng = rng or random.Random(0)
    fp = plan.footprint
    out = []
    for r in plan.rooms:
        kind = P.ROOMS[r.type].window
        if not kind:
            continue
        _w, sill, height, _s = WINDOWS[kind]
        for axis, c, outward, lo, hi in L.window_parts(r.rect, fp, plan.walls):
            # keep DOOR_CLEAR from a door on the same wall; a terrace door's whole stretch of wall stays plain
            cuts = [d.wall if d.wall else (d.s0 - DOOR_CLEAR, d.s1 + DOOR_CLEAR)
                    for d in doors if d.axis == axis and abs(d.c - c) < EPS]
            for a, b in _minus(lo, hi, cuts):
                for s0, s1 in fill(a, b, kind, rng):
                    out.append(Window(r.id, axis, c, s0, s1, sill, height, kind, outward))
    return out
