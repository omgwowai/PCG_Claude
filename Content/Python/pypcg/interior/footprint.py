"""PyInterior footprint (spec 2026-10-28 §4.1). A house's closed footprint spline -> the house's local frame (the front
faces the actor's forward: local -y) -> a cell set on the `grid` (cell centres inside the spline polygon, the largest
4-connected piece, holes filled, diagonal pinches closed) -> rectangular wings (greedy largest rectangles; a wing thinner
than `min_wing` is dropped and the rest decomposed again) -> the rectilinear outline and its wall segments. Pure."""
import math
from dataclasses import dataclass

EPS = 1e-6
MIN_EXTENT = 450.0          # cm: the short side of the bounding box, after the outline snaps to the grid
MIN_LONG = 500.0            # cm: its long side -- a 4.5 x 4.5 m square holds no studio (living room + bathroom)
MIN_AREA_M2 = 20.0


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def area(self):
        return self.w * self.h

    @property
    def cx(self):
        return 0.5 * (self.x0 + self.x1)

    @property
    def cy(self):
        return 0.5 * (self.y0 + self.y1)

    @property
    def short(self):
        return min(self.w, self.h)

    @property
    def long(self):
        return max(self.w, self.h)

    def overlaps(self, o):
        return self.x0 < o.x1 - EPS and o.x0 < self.x1 - EPS and self.y0 < o.y1 - EPS and o.y0 < self.y1 - EPS

    def contains(self, x, y):
        return self.x0 - EPS <= x <= self.x1 + EPS and self.y0 - EPS <= y <= self.y1 + EPS

    def inside(self, o):
        """self lies within o."""
        return self.x0 >= o.x0 - EPS and self.y0 >= o.y0 - EPS and self.x1 <= o.x1 + EPS and self.y1 <= o.y1 + EPS

    def shrink(self, l, b, r, t):
        return Rect(self.x0 + l, self.y0 + b, self.x1 - r, self.y1 - t)

    def shared(self, o):
        """The edge two touching rectangles share: ("x", c, a0, a1) = the vertical line x = c from y a0 to a1, ("y", c, a0, a1)
        = the horizontal line y = c from x a0 to a1; None when they share no edge of positive length."""
        for mine, theirs in ((self.x1, o.x0), (self.x0, o.x1)):
            if abs(mine - theirs) < EPS:
                a0, a1 = max(self.y0, o.y0), min(self.y1, o.y1)
                if a1 - a0 > EPS:
                    return ("x", mine, a0, a1)
        for mine, theirs in ((self.y1, o.y0), (self.y0, o.y1)):
            if abs(mine - theirs) < EPS:
                a0, a1 = max(self.x0, o.x0), min(self.x1, o.x1)
                if a1 - a0 > EPS:
                    return ("y", mine, a0, a1)
        return None

    def edges(self):
        """The four sides as (axis, c, a0, a1, outward): bottom, right, top, left."""
        return [("y", self.y0, self.x0, self.x1, -1), ("x", self.x1, self.y0, self.y1, 1),
                ("y", self.y1, self.x0, self.x1, 1), ("x", self.x0, self.y0, self.y1, -1)]


@dataclass(frozen=True)
class Seg:
    """A straight piece of the outline: axis "y" = horizontal (y = c, x from a0 to a1), "x" = vertical (x = c, y from a0 to
    a1); `normal` the outward side along the other axis (-1 / +1); convex0 / convex1 the corner at the a0 / a1 end."""
    axis: str
    c: float
    a0: float
    a1: float
    normal: int
    convex0: bool
    convex1: bool

    @property
    def length(self):
        return self.a1 - self.a0


class Frame:
    """The house's local frame: origin at the actor, e_y = -forward, e_x = e_y turned -90 degrees (right-handed)."""

    def __init__(self, origin, yaw_deg):
        self.origin = tuple(float(v) for v in origin[:3]) if len(origin) >= 3 else (float(origin[0]), float(origin[1]), 0.0)
        self.yaw = float(yaw_deg)
        a = math.radians(self.yaw)
        self.ex = (-math.sin(a), math.cos(a))
        self.ey = (-math.cos(a), -math.sin(a))

    def local(self, p):
        dx, dy = p[0] - self.origin[0], p[1] - self.origin[1]
        return (dx * self.ex[0] + dy * self.ex[1], dx * self.ey[0] + dy * self.ey[1])

    def world(self, x, y, z=0.0):
        return (self.origin[0] + x * self.ex[0] + y * self.ey[0], self.origin[1] + x * self.ex[1] + y * self.ey[1],
                self.origin[2] + z)

    def yaw_world(self, local_yaw):
        """A local direction at angle t (from +x towards +y) points along world yaw a + 90 + t."""
        return self.yaw + 90.0 + local_yaw


@dataclass
class Footprint:
    cells: frozenset
    grid: float
    wings: list
    frame: Frame
    poly: list

    @property
    def origin(self):
        return self.frame.origin

    @property
    def yaw(self):
        return self.frame.yaw

    @property
    def area_m2(self):
        return len(self.cells) * self.grid * self.grid / 1e4

    @property
    def area(self):
        return len(self.cells) * self.grid * self.grid

    def to_world(self, x, y, z=0.0):
        return self.frame.world(x, y, z)

    def yaw_world(self, local_yaw):
        return self.frame.yaw_world(local_yaw)

    def segments(self):
        return outline_segments(self.poly)

    @property
    def front(self):
        return sorted(((s.a0, s.a1, s.c) for s in self.segments() if s.axis == "y" and s.normal < 0),
                      key=lambda t: (t[2], t[0]))

    def bbox(self):
        xs, ys = [p[0] for p in self.poly], [p[1] for p in self.poly]
        return Rect(min(xs), min(ys), max(xs), max(ys))


def _inside(poly, x, y):
    n, c = len(poly), False
    for k in range(n):
        (x0, y0), (x1, y1) = poly[k], poly[(k + 1) % n]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                c = not c
    return c


def rasterise(poly, grid):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    i0, i1 = int(math.floor(min(xs) / grid)) - 1, int(math.ceil(max(xs) / grid)) + 1
    j0, j1 = int(math.floor(min(ys) / grid)) - 1, int(math.ceil(max(ys) / grid)) + 1
    return {(i, j) for i in range(i0, i1) for j in range(j0, j1) if _inside(poly, (i + 0.5) * grid, (j + 0.5) * grid)}


def largest_component(cells):
    left, best = set(cells), set()
    while left:
        seed = min(left)
        comp, todo = {seed}, [seed]
        left.discard(seed)
        while todo:
            i, j = todo.pop()
            for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if n in left:
                    left.discard(n)
                    comp.add(n)
                    todo.append(n)
        if len(comp) > len(best) or (len(comp) == len(best) and min(comp) < min(best)):
            best = comp
    return best


def fill_holes(cells):
    if not cells:
        return set()
    i0, i1 = min(c[0] for c in cells) - 1, max(c[0] for c in cells) + 1
    j0, j1 = min(c[1] for c in cells) - 1, max(c[1] for c in cells) + 1
    outside, todo = {(i0, j0)}, [(i0, j0)]
    while todo:
        i, j = todo.pop()
        for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if i0 <= n[0] <= i1 and j0 <= n[1] <= j1 and n not in cells and n not in outside:
                outside.add(n)
                todo.append(n)
    return {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1) if (i, j) not in outside}


def close_pinches(cells):
    cells = set(cells)
    while True:
        added = False
        for (i, j) in sorted(cells):
            # the corner at (i + 1, j + 1): (i, j) and (i + 1, j + 1) in, (i + 1, j) and (i, j + 1) out
            if (i + 1, j + 1) in cells and (i + 1, j) not in cells and (i, j + 1) not in cells:
                cells.add((i + 1, j))
                added = True
            # the corner at (i, j + 1): (i, j) and (i - 1, j + 1) in, (i - 1, j) and (i, j + 1) out
            if (i - 1, j + 1) in cells and (i - 1, j) not in cells and (i, j + 1) not in cells:
                cells.add((i, j + 1))
                added = True
        if not added:
            return cells


def clean(cells):
    return close_pinches(fill_holes(largest_component(cells)))


def _max_rect(cells):
    """The largest rectangle of cells, (i0, j0, i1, j1) with exclusive ends; ties go to the lowest (j0, i0)."""
    i_lo, i_hi = min(c[0] for c in cells), max(c[0] for c in cells)
    j_lo, j_hi = min(c[1] for c in cells), max(c[1] for c in cells)
    heights = {i: 0 for i in range(i_lo, i_hi + 2)}
    best = None
    for j in range(j_lo, j_hi + 1):
        for i in range(i_lo, i_hi + 1):
            heights[i] = heights[i] + 1 if (i, j) in cells else 0
        stack = []           # (start column, height)
        for i in range(i_lo, i_hi + 2):
            h = heights[i] if i <= i_hi else 0
            start = i
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                if sh:
                    cand = (sh * (i - s), -(j - sh + 1), -s)
                    if best is None or cand > best[0]:
                        best = (cand, (s, j - sh + 1, i, j + 1))
                start = s
            stack.append((start, h))
    return best[1]


def decompose(cells):
    left, out = set(cells), []
    while left:
        i0, j0, i1, j1 = _max_rect(left)
        out.append((i0, j0, i1, j1))
        for i in range(i0, i1):
            for j in range(j0, j1):
                left.discard((i, j))
    return out


def outline(cells, grid):
    """The CCW outline of a hole-free, pinch-free cell set, collinear vertices dropped, in cm."""
    nxt = {}
    for (i, j) in cells:
        if (i, j - 1) not in cells:
            nxt[(i, j)] = (i + 1, j)
        if (i + 1, j) not in cells:
            nxt[(i + 1, j)] = (i + 1, j + 1)
        if (i, j + 1) not in cells:
            nxt[(i + 1, j + 1)] = (i, j + 1)
        if (i - 1, j) not in cells:
            nxt[(i, j + 1)] = (i, j)
    start = min(nxt, key=lambda v: (v[1], v[0]))
    loop, v = [start], nxt[start]
    while v != start:
        loop.append(v)
        v = nxt[v]
    keep = []
    n = len(loop)
    for k in range(n):
        a, b, c = loop[k - 1], loop[k], loop[(k + 1) % n]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) != 0:
            keep.append(b)
    k0 = min(range(len(keep)), key=lambda k: (keep[k][1], keep[k][0]))
    keep = keep[k0:] + keep[:k0]
    return [(i * grid, j * grid) for i, j in keep]


def outline_segments(poly):
    n = len(poly)
    convex = []
    for k in range(n):
        a, b, c = poly[k - 1], poly[k], poly[(k + 1) % n]
        convex.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) > 0)
    segs = []
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        cp, cq = convex[k], convex[(k + 1) % n]
        if abs(p[1] - q[1]) < EPS:
            fwd = q[0] > p[0]
            segs.append(Seg("y", p[1], min(p[0], q[0]), max(p[0], q[0]), -1 if fwd else 1,
                            cp if fwd else cq, cq if fwd else cp))
        else:
            fwd = q[1] > p[1]
            segs.append(Seg("x", p[0], min(p[1], q[1]), max(p[1], q[1]), 1 if fwd else -1,
                            cp if fwd else cq, cq if fwd else cp))
    return segs


def build(points_world, origin, yaw_deg, grid=50.0, min_wing=250.0):
    """The house's footprint, or None when the spline is degenerate or its cells are smaller than MIN_EXTENT x MIN_LONG
    (either way round) or MIN_AREA_M2."""
    if len(points_world) < 3:
        return None
    frame = Frame(origin, yaw_deg)
    poly = [frame.local(p) for p in points_world]
    return from_cells(rasterise(poly, grid), grid, frame, min_wing)


def from_cells(cells, grid, frame, min_wing=250.0):
    """A footprint from cells in `frame` (an upper floor's clipped cells, a rasterised spline): the largest piece, holes
    filled, wings thinner than `min_wing` dropped; None below MIN_EXTENT x MIN_LONG / MIN_AREA_M2."""
    cells = clean(set(cells)) if cells else set()
    while cells:
        rects = decompose(cells)
        thin = [r for r in rects if min(r[2] - r[0], r[3] - r[1]) * grid < min_wing - EPS]
        if not thin:
            break
        for i0, j0, i1, j1 in thin:
            for i in range(i0, i1):
                for j in range(j0, j1):
                    cells.discard((i, j))
        cells = clean(cells) if cells else cells
    if not cells:
        return None
    i_lo, i_hi = min(c[0] for c in cells), max(c[0] for c in cells) + 1
    j_lo, j_hi = min(c[1] for c in cells), max(c[1] for c in cells) + 1
    short, long_ = sorted(((i_hi - i_lo) * grid, (j_hi - j_lo) * grid))
    if short < MIN_EXTENT - EPS or long_ < MIN_LONG - EPS or len(cells) * grid * grid / 1e4 < MIN_AREA_M2 - EPS:
        return None
    wings = [Rect(i0 * grid, j0 * grid, i1 * grid, j1 * grid) for i0, j0, i1, j1 in decompose(cells)]
    return Footprint(frozenset(cells), float(grid), wings, frame, outline(cells, grid))
