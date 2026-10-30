"""PyInterior terraces (spec 2026-10-29 §8): the roof of a lower floor that the floor above leaves open.

A terrace is a deck on the lower floor's roof with a railing along its open edges (the ones over the lower floor's outer
walls), a sliding glass door from the room of the upper floor it touches (doors.terrace_doors), and outdoor furniture by
its size: a table with two to four chairs and a plant when it is at least SET_SHORT across and SET_AREA large, a plant from
PLANT_AREA, nothing on a strip narrower than NARROW or on a terrace no room opens onto. The furniture keeps INSET from the
deck's edges and the floor in front of the door free. `parts`: its slab (the lower floor's roof), deck, railing (RAIL_H
high, metal posts at most POST apart, a top and a middle rail) and furniture. Pure."""
import math
from dataclasses import dataclass, field

from pypcg.interior import assemble as A
from pypcg.interior import catalog as C
from pypcg.interior import furnish as FU
from pypcg.interior import layout as L
from pypcg.interior.footprint import EPS, Rect

INSET = 15.0                 # furniture keeps this far from the deck's edges (the railing, the wall)
NARROW = 120.0               # a strip narrower than this gets the railing alone
SET_SHORT = 200.0            # a table set from this short side ...
SET_AREA = 6e4               # ... and this area (cm2)
PLANT_AREA = 3e4             # a plant from this area
DOOR_FRONT = 120.0           # the deck kept free in front of the door, this deep ...
DOOR_SIDE = 30.0             # ... and this much wider than the door on each side
GAP = 10.0                   # between the table and a chair
STEP = 10.0
DECK = 2.0                   # the deck's boards over the slab
DECK_MATERIAL = "Floor_Deck"
RAIL_H = 105.0               # the railing's height
RAIL_MID = 55.0              # its middle rail
RAIL_T = 5.0                 # posts and rails, square
RAIL_IN = 5.0                # the railing's line this far inside the edge
POST = 150.0                 # at most between two posts


@dataclass
class Terrace:
    level: int               # the floor it is walked out onto
    rect: Rect               # house-local
    door: object = None      # its doors.Door (kind "terrace"); None when no room opens onto it
    places: list = field(default_factory=list)    # furnish.Placement, room -1
    rails: list = field(default_factory=list)     # [(axis, c, lo, hi, outward)]: the open edges, railed


def _on_edge(d, rect):
    """Door d lies on a side of rect."""
    if d.axis == "y":
        return min(abs(d.c - rect.y0), abs(d.c - rect.y1)) < EPS and d.s0 >= rect.x0 - EPS and d.s1 <= rect.x1 + EPS
    return min(abs(d.c - rect.x0), abs(d.c - rect.x1)) < EPS and d.s0 >= rect.y0 - EPS and d.s1 <= rect.y1 + EPS


def door_zone(d, rect):
    """The deck in front of the terrace door that is kept free."""
    lo, hi = d.s0 - DOOR_SIDE, d.s1 + DOOR_SIDE
    if d.axis == "y":
        return Rect(lo, d.c, hi, d.c + DOOR_FRONT) if abs(d.c - rect.y0) < EPS else Rect(lo, d.c - DOOR_FRONT, hi, d.c)
    return Rect(d.c, lo, d.c + DOOR_FRONT, hi) if abs(d.c - rect.x0) < EPS else Rect(d.c - DOOR_FRONT, lo, d.c, hi)


def _place(item, x, y, yaw):
    it = C.ITEMS[item]
    return FU.Placement(item, -1, x, y, yaw, it.w, it.d, it.h, 0.0, -1, "terrace")


def _seats(tx, ty, n, along_x):
    """[(item, x, y, yaw)]: Table_2 at (tx, ty) with n armchairs facing it: the first two on its sides along the set's
    axis, then across."""
    t = C.ITEMS["Table_2"]
    a = C.ITEMS["Armchair"]
    hu, hv = (t.w / 2, t.d / 2) if along_x else (t.d / 2, t.w / 2)      # the table's half sizes along / across
    du, dv = hu + GAP + a.d / 2, hv + GAP + a.d / 2
    if along_x:
        seats = [(tx - du, ty, -90.0), (tx + du, ty, 90.0), (tx, ty - dv, 0.0), (tx, ty + dv, 180.0)]
    else:
        seats = [(tx, ty - du, 0.0), (tx, ty + du, 180.0), (tx - dv, ty, -90.0), (tx + dv, ty, 90.0)]
    return [("Table_2", tx, ty, 0.0 if along_x else 90.0)] + [("Armchair", x, y, yaw) for x, y, yaw in seats[:n]]


def _set(tx, ty, n, along_x):
    return [_place(*s) for s in _seats(tx, ty, n, along_x)]


def _reach(n, along_x):
    """(x0, y0, x1, y1): how far the table set reaches from its table's centre."""
    rs = [_place(*s).rect() for s in _seats(0.0, 0.0, n, along_x)]
    return min(r.x0 for r in rs), min(r.y0 for r in rs), max(r.x1 for r in rs), max(r.y1 for r in rs)


def _free(ps, deck, keep):
    return all(p.rect().inside(deck) and not p.rect().overlaps(keep) for p in ps) and \
        all(not a.rect().overlaps(b.rect()) for i, a in enumerate(ps) for b in ps[i + 1:])


def _table_set(deck, keep, rng):
    """The table set with the most chairs (four, three, two) that fits the deck clear of the door, as near the middle as
    it goes (the seed breaks ties); [] when none fits. A set reaching over the deck's edge (by more than a centimetre)
    is not built: it never fits, so no seed is drawn for it either way."""
    for n in (4, 3, 2):
        best = None
        for along_x in ((True, False) if deck.w >= deck.h else (False, True)):
            rx0, ry0, rx1, ry1 = _reach(n, along_x)
            y = deck.y0
            while y <= deck.y1 + EPS:
                if y + ry0 >= deck.y0 - 1.0 and y + ry1 <= deck.y1 + 1.0:
                    x = deck.x0
                    while x <= deck.x1 + EPS:
                        if x + rx0 >= deck.x0 - 1.0 and x + rx1 <= deck.x1 + 1.0:
                            ps = _set(x, y, n, along_x)
                            if _free(ps, deck, keep):
                                key = ((x - deck.cx) ** 2 + (y - deck.cy) ** 2 + rng.random() * 1e-3, not along_x)
                                if best is None or key < best[0]:
                                    best = (key, ps)
                        x += STEP
                y += STEP
        if best is not None:
            return best[1]
    return []


def _plant(deck, keep, taken, door):
    """A plant in a free corner of the deck, the one farthest from the door; None when no corner is free."""
    h = C.ITEMS["Plant"].w / 2
    best = None
    for x in (deck.x0 + h, deck.x1 - h):
        for y in (deck.y0 + h, deck.y1 - h):
            p = _place("Plant", x, y, 0.0)
            if not _free(taken + [p], deck, keep):
                continue
            mx, my = door.point()
            key = -((x - mx) ** 2 + (y - my) ** 2)
            if best is None or key < best[0]:
                best = (key, p)
    return best[1] if best else None


def _rails(rect, below):
    """The stretches of the terrace's edges over the lower floor's outer walls: their outside is not on its roof."""
    return [(axis, c, lo, hi, out) for axis, c, a0, a1, out in rect.edges()
            for lo, hi in L.exterior_parts(below, axis, c, a0, a1, out)]


def plan_terraces(below, rects, plan, doors, rng):
    """[Terrace] for the terrace rects of floor `plan` (on the roof of the floor below, footprint `below`): each with the
    terrace door on its edge (from `doors`), its railed edges and its furniture."""
    out = []
    for r in rects:
        d = next((d for d in doors if d.kind == "terrace" and _on_edge(d, r)), None)
        t = Terrace(plan.level, r, d, [], _rails(r, below))
        if d is not None and r.short >= NARROW - EPS:
            deck, keep = r.shrink(INSET, INSET, INSET, INSET), door_zone(d, r)
            if r.short >= SET_SHORT - EPS and r.area >= SET_AREA - EPS:
                t.places = _table_set(deck, keep, rng)
            if r.area >= PLANT_AREA - EPS:
                p = _plant(deck, keep, t.places, d)
                if p is not None:
                    t.places.append(p)
        out.append(t)
    return out


# ---------------------------------------------------------------- parts

def railing(out, axis, c, lo, hi, inward, pal, z=0.0):
    """A metal railing RAIL_IN inside the line (axis, c) from lo to hi, towards `inward` (-1 / +1 across the line):
    posts at most POST apart (one at each end), a top and a middle rail; its base at height z."""
    if hi - lo <= EPS:
        return
    m = c + inward * RAIL_IN
    h = 0.5 * RAIL_T
    lo, hi = lo + h, hi - h
    n = max(1, int(math.ceil((hi - lo) / POST - 1e-9)))
    for k in range(n + 1):
        a = lo + (hi - lo) * k / n
        out.box(A._along(axis, m, a - h, a + h, -h, h), z, z + RAIL_H - RAIL_T, pal["steel"], "railing")
        if out.items and out.items[-1]["role"] == "railing":
            out.items[-1]["part"] = "post"
    for z0 in (RAIL_H - RAIL_T, RAIL_MID - RAIL_T / 2):
        out.box(A._along(axis, m, lo - h, hi + h, -h, h), z + z0, z + z0 + RAIL_T, pal["steel"], "railing")


def parts(terraces, out, pal, furniture=True, real=True):
    """The terraces' parts in `out` (the upper floor's frame): the slab they stand on (the lower floor's roof, the facade's
    colour), the deck, the railing on the open edges, the furniture."""
    for t in terraces:
        out.box(t.rect, -A.SLAB, 0.0, pal["facade"], "terrace_slab")
        out.box(t.rect, 0.0, DECK, DECK_MATERIAL, "terrace_deck")
        for axis, c, lo, hi, outward in t.rails:
            railing(out, axis, c, lo, hi, -outward, pal, DECK)
        if furniture:
            A._furniture(out, t.places, pal, real)
