"""Offline stand-ins for the editor services a stage reaches through ctx.ops (ruling N2)."""
from pypcg import geo


def _half(ring, a, b, side):
    def s(p):
        return side * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
    out = []
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        sp, sq = s(p), s(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


class FakeOps:
    """cut_with_paths for convex rings and straight paths (the line through each path's ends), and
    intersection of convex rings (Sutherland-Hodgman)."""

    def cut_with_paths(self, ring, paths):
        pieces = [list(ring)]
        for path in paths:
            a, b = path[0], path[-1]
            nxt = []
            for r in pieces:
                for side in (1, -1):
                    part = _half(r, a, b, side)
                    if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                        nxt.append(geo.ccw(part))
            pieces = nxt
        return pieces

    def intersection(self, rings_a, rings_b):
        out = []
        for a in rings_a:
            for b in rings_b:
                part, b = list(geo.ccw(a)), geo.ccw(b)
                for i in range(len(b)):
                    part = _half(part, b[i], b[(i + 1) % len(b)], 1) if len(part) >= 3 else []
                if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                    out.append(geo.Polygon(geo.ccw(part)))
        return out


class FlatTerrain:
    """A surface at constant height."""

    def __init__(self, z=0.0):
        self.z = z

    def height(self, x, y):
        return self.z


class RibbonOps:
    """Offline stand-in for the Clipper2 half of a road outline (`pypcg.ue.ops.Ops`).

    A real polygon offset is Clipper2's `InflatePaths`; offline this supports the one shape stage 7
    actually asks for -- the ribbon of a straight or gently turning path. `path_offset` returns the
    band within `distance` of the path (its two side offsets joined, capped flat at both ends), and
    `offset`/`difference`/`union` treat rings as axis-aligned boxes.

    It is deliberately a weaker oracle than the engine's: it exists so the *algorithm* can be tested
    without the editor, and every number it produces is re-measured against the real booleans in the
    in-editor probes. `union` merges overlapping or touching boxes **pairwise** and keeps disjoint
    ones apart, so two roads far apart stay two footprints rather than one bounding box.
    """

    def path_offset(self, path, distance, end="butt", join="square", miter_limit=2.0):
        left, right = _sides(path, 0.5 * distance)
        if not left:
            return []
        ring = left + list(reversed(right))
        if len(ring) < 3:
            return []
        return [geo.Polygon(geo.ccw(ring))]

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        out = []
        for r in rings:
            (x0, y0), (x1, y1) = geo.bbox(r)
            if distance <= 0.0 and (x1 - x0) + 2 * distance <= 0:
                continue
            out.append(geo.Polygon([(x0 - distance, y0 - distance), (x1 + distance, y0 - distance),
                                    (x1 + distance, y1 + distance), (x0 - distance, y1 + distance)]))
        return out

    def difference(self, rings_a, rings_b):
        """Box minus boxes, as disjoint boxes (a proper sweep, not one bounding box)."""
        out = []
        for a in rings_a:
            out.extend(_box_difference(geo.bbox(a), [geo.bbox(b) for b in rings_b]))
        return [geo.Polygon(_box_ring(b)) for b in out]

    def union(self, rings):
        """Merge boxes that overlap, pairwise, until nothing more merges."""
        boxes = [geo.bbox(r) for r in rings]
        changed = True
        while changed:
            changed = False
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    if _boxes_overlap(boxes[i], boxes[j]):
                        boxes[i] = ((min(boxes[i][0][0], boxes[j][0][0]), min(boxes[i][0][1], boxes[j][0][1])),
                                    (max(boxes[i][1][0], boxes[j][1][0]), max(boxes[i][1][1], boxes[j][1][1])))
                        del boxes[j]
                        changed = True
                        break
                if changed:
                    break
        return [geo.Polygon(_box_ring(b)) for b in boxes]


def _box_ring(box):
    (x0, y0), (x1, y1) = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _boxes_overlap(a, b):
    return not (b[1][0] <= a[0][0] or b[0][0] >= a[1][0] or b[1][1] <= a[0][1] or b[0][1] >= a[1][1])


def _box_difference(a, cutters):
    """`a` minus every cutter box, as disjoint boxes."""
    parts = [a]
    for c in cutters:
        nxt = []
        for p in parts:
            nxt.extend(_one_difference(p, c))
        parts = [q for q in nxt if q[1][0] - q[0][0] > 1e-9 and q[1][1] - q[0][1] > 1e-9]
    return parts


def _one_difference(a, c):
    """One box minus one box: up to four slabs."""
    (ax0, ay0), (ax1, ay1) = a
    (cx0, cy0), (cx1, cy1) = c
    if cx1 <= ax0 or cx0 >= ax1 or cy1 <= ay0 or cy0 >= ay1:
        return [a]
    out = []
    if ay0 < cy0:
        out.append(((ax0, ay0), (ax1, cy0)))
    if ay1 > cy1:
        out.append(((ax0, cy1), (ax1, ay1)))
    lo, hi = max(ax0, cx0), min(ax1, cx1)
    if lo < hi:
        ym0, ym1 = max(ay0, cy0), min(ay1, cy1)
        if ax0 < lo:
            out.append(((ax0, ym0), (lo, ym1)))
        if hi < ax1:
            out.append(((hi, ym0), (ax1, ym1)))
    return out


def _seg_normal(a, b, distance):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (dx * dx + dy * dy) ** 0.5
    if n < 1e-12:
        return (0.0, 0.0)
    return (-dy / n * distance, dx / n * distance)


def _sides(path, distance):
    """The path's two side offsets, left then right, for an open polyline."""
    if len(path) < 2:
        return [], []
    left, right = [], []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        nx, ny = _seg_normal(a, b, distance)
        if not left:
            left.append((a[0] + nx, a[1] + ny))
            right.append((a[0] - nx, a[1] - ny))
        left.append((b[0] + nx, b[1] + ny))
        right.append((b[0] - nx, b[1] - ny))
    return left, right
