"""PyInterior doors (spec 2026-10-28 §4.5): the passages along the layout's connection tree, the front door, and extra
openings between adjacent open-plan rooms.

Each passage sits on the wall two rooms share, inside both rooms' clear width and MARGIN from the wall's ends. A door with a
leaf (bedrooms 90, wet rooms 80) goes to the end nearer the point the parent room is entered from, hinged at that end and
opening into the child room; a doorway (into a corridor, 90) and an opening (public rooms, up to 180) are centred and have no
leaf (a wet room's door slides into the wall). The front door (100) is centred on the clear part of the entry room's front wall -- or, when that wall is the room's only
window wall, at its end nearer the middle of the house. `swing` gives the floor a passage
needs kept free: the leaf's sweep, or the approach in front of a doorway / opening. Pure."""
from dataclasses import dataclass

from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.interior.footprint import EPS, Rect

WIDTH = {"front": 100.0, "door": 90.0, "bath": 80.0, "doorway": 90.0}
OPENING_MAX = 180.0
OPENING_MIN = 100.0
MIN_WIDTH = 80.0             # a passage narrower than this is not placed
MARGIN = 15.0                # from the ends of the shared wall
JAMB = 5.0                   # from the clear face of a crossing wall
DOOR_H = 210.0
APPROACH = 60.0              # the clear floor in front of a doorway / opening


@dataclass(frozen=True)
class Door:
    a: object                # the parent room's id (None: the front door, from outside)
    b: int                   # the room it leads into
    axis: str                # "x": on the vertical wall line x = c; "y": on the horizontal line y = c
    c: float
    s0: float
    s1: float
    kind: str                # front | door | bath | doorway | opening
    tree: bool = True        # on the connection tree (False: an extra opening)
    hinge: int = 0           # the leaf is hinged at s0 (0) or at s1 (1)

    @property
    def leaf(self):
        return self.kind in ("front", "door", "bath")

    @property
    def sliding(self):
        """A bathroom's door slides into the wall (a pocket door): a narrow room keeps its floor."""
        return self.kind == "bath"

    @property
    def width(self):
        return self.s1 - self.s0

    @property
    def mid(self):
        return 0.5 * (self.s0 + self.s1)

    def point(self):
        return (self.c, self.mid) if self.axis == "x" else (self.mid, self.c)


def _along(rect, axis):
    """A rectangle's extent along a wall line of this axis ("x" lines run along y)."""
    return (rect.y0, rect.y1) if axis == "x" else (rect.x0, rect.x1)


def interval(plan, a, b):
    """(axis, c, lo, hi): where on the wall rooms a and b share a passage may go, or None."""
    sh = a.rect.shared(b.rect)
    if sh is None:
        return None
    axis, c, a0, a1 = sh
    fp, walls = plan.footprint, plan.walls
    ca, cb = L.clear_rect(a.rect, fp, walls), L.clear_rect(b.rect, fp, walls)
    lo = max(a0 + MARGIN, _along(ca, axis)[0] + JAMB, _along(cb, axis)[0] + JAMB)
    hi = min(a1 - MARGIN, _along(ca, axis)[1] - JAMB, _along(cb, axis)[1] - JAMB)
    return (axis, c, lo, hi) if hi - lo > EPS else None


def _place(kind, iv, near):
    axis, c, lo, hi = iv
    room = hi - lo
    if kind == "opening":
        w = min(OPENING_MAX, room - 20.0)
        if w < OPENING_MIN - EPS:
            w = min(WIDTH["doorway"], room)
        if w < MIN_WIDTH - EPS:
            return None
        m = 0.5 * (lo + hi)
        return (m - 0.5 * w, m + 0.5 * w, 0)
    w = min(WIDTH[kind], room)
    if w < MIN_WIDTH - EPS:
        return None
    if kind == "doorway":
        m = 0.5 * (lo + hi)
        return (m - 0.5 * w, m + 0.5 * w, 0)
    # a leaf door at the end nearer where the parent is entered, hinged at that end
    if near is None or abs(near - lo) <= abs(near - hi):
        return (lo, lo + w, 0)
    return (hi - w, hi, 1)


def connect(plan, rng=None):
    """The house's passages: [Door] -- the front door, one tree passage into every other room, extra openings."""
    by = {r.id: r for r in plan.rooms}
    fp, walls = plan.footprint, plan.walls
    out = []
    # the front door, centred on the clear part of the entry room's front wall
    fr = by[plan.front_room]
    cf = L.clear_rect(fr.rect, fp, walls)
    x0, x1, y = plan.entry
    lo, hi = max(x0 + MARGIN, cf.x0 + JAMB), min(x1 - MARGIN, cf.x1 - JAMB)
    w = min(WIDTH["front"], hi - lo)
    m = 0.5 * (lo + hi)
    s0, s1 = m - 0.5 * w, m + 0.5 * w
    # a room whose front wall is its only window wall keeps that wall for windows: the door goes to the end nearer the
    # middle of the house (where the corridor usually starts)
    elsewhere = [b - a for axis, c, _o, a, b in L.window_parts(fr.rect, fp, walls) if not (axis == "y" and abs(c - y) < EPS)]
    if max(elsewhere, default=0.0) < L.WINDOW_MIN - EPS:
        cx = fp.bbox().cx
        s0, s1 = (lo, lo + w) if abs(lo - cx) <= abs(hi - cx) else (hi - w, hi)
    front = Door(None, fr.id, "y", y, s0, s1, "front", True, 0)
    out.append(front)
    entered = {fr.id: front.point()}
    # tree passages in breadth-first order, each placed near where its parent is entered
    kids = {}
    for rid, pid in plan.parents.items():
        if pid is not None:
            kids.setdefault(pid, []).append(rid)
    todo = [fr.id]
    while todo:
        pid = todo.pop(0)
        for rid in sorted(kids.get(pid, [])):
            a, b = by[pid], by[rid]
            iv = interval(plan, a, b)
            kind = L.passage(a.type, b.type)
            ep = entered[pid]
            near = ep[1] if iv and iv[0] == "x" else (ep[0] if iv else None)
            spot = _place(kind, iv, near) if iv else None
            if spot is None:
                continue
            d = Door(pid, rid, iv[0], iv[1], spot[0], spot[1], kind, True, spot[2])
            out.append(d)
            entered[rid] = d.point()
            todo.append(rid)
    # open-plan rooms side by side get an opening even when the tree joins them another way
    linked = {frozenset((d.a, d.b)) for d in out if d.a is not None}
    rooms = plan.rooms
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if frozenset((a.type, b.type)) not in P.OPEN or frozenset((a.id, b.id)) in linked:
                continue
            if L.shared_length(a.rect, b.rect) < L.SPAN["opening"] - EPS:
                continue
            iv = interval(plan, a, b)
            spot = _place("opening", iv, None) if iv else None
            if spot is not None:
                out.append(Door(a.id, b.id, iv[0], iv[1], spot[0], spot[1], "opening", False, 0))
    return out


def swing(door, room, plan):
    """The floor of `room` a passage needs kept free: the leaf's sweep (a square as wide as the door) for a door,
    APPROACH in front of a doorway or an opening -- measured from the room's side of the wall line."""
    depth = door.width if door.leaf and not door.sliding else APPROACH
    R = room.rect
    if door.axis == "x":
        if R.x0 >= door.c - EPS:
            return Rect(door.c, door.s0, min(R.x1, door.c + depth + 0.5 * plan.walls["int"]), door.s1)
        return Rect(max(R.x0, door.c - depth - 0.5 * plan.walls["int"]), door.s0, door.c, door.s1)
    t = plan.walls["ext"] if door.kind == "front" else 0.5 * plan.walls["int"]
    if R.y0 >= door.c - EPS:
        return Rect(door.s0, door.c, door.s1, min(R.y1, door.c + depth + t))
    return Rect(door.s0, max(R.y0, door.c - depth - t), door.s1, door.c)
