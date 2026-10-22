"""2D geometry for the world stages: polylines, a bucketed segment index, intersections, rectangles and a ring index."""
import bisect
import math


def dist2d(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def length(pts):
    return sum(dist2d(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def cumulative(pts):
    out = [0.0]
    for i in range(1, len(pts)):
        out.append(out[-1] + dist2d(pts[i - 1], pts[i]))
    return out


def lerp(a, b, t):
    return tuple(a[c] + (b[c] - a[c]) * t for c in range(len(a)))


def yaw_deg(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def at_distance(pts, cum, s):
    """((x, y), yaw) at arc length s along pts (clamped)."""
    s = min(max(s, 0.0), cum[-1])
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    p = lerp(pts[i][:2], pts[i + 1][:2], t)
    return (p[0], p[1]), yaw_deg(pts[i], pts[i + 1])


def resample(pts, step):
    """Evenly spaced points (spacing <= step) from the first to the last; every coordinate is interpolated."""
    pts = [tuple(p) for p in pts]
    if len(pts) < 2:
        return pts
    cum = cumulative(pts)
    total = cum[-1]
    if total == 0:
        return [pts[0]]
    m = max(1, int(math.ceil(total / step)))
    out, seg = [], 0
    for q in range(m + 1):
        s = total * q / m
        while seg < len(pts) - 2 and cum[seg + 1] < s:
            seg += 1
        span = cum[seg + 1] - cum[seg]
        t = 0.0 if span == 0 else (s - cum[seg]) / span
        out.append(lerp(pts[seg], pts[seg + 1], min(1.0, max(0.0, t))))
    return out


def chaikin(pts, iterations=2):
    """Corner cutting that keeps both end points."""
    pts = [tuple(p) for p in pts]
    for _ in range(iterations):
        if len(pts) < 3:
            return pts
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append(lerp(a, b, 0.25))
            out.append(lerp(a, b, 0.75))
        out.append(pts[-1])
        pts = out
    return pts


def moving_average(vals, half):
    n = len(vals)
    pre = [0.0]
    for v in vals:
        pre.append(pre[-1] + v)
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append((pre[b] - pre[a]) / (b - a))
    return out


def seg_point(px, py, ax, ay, bx, by):
    """(distance, t) from (px, py) to the segment a-b, t the parameter of the closest point."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


class SegmentIndex:
    """Segments bucketed on a uniform grid, for nearest-segment queries within a radius."""

    def __init__(self, cell=2000.0):
        self.cell = float(cell)
        self.segs = []
        self.buckets = {}

    def add(self, a, b, payload=None):
        idx = len(self.segs)
        self.segs.append((a[0], a[1], b[0], b[1], payload))
        c = self.cell
        for bx in range(math.floor(min(a[0], b[0]) / c), math.floor(max(a[0], b[0]) / c) + 1):
            for by in range(math.floor(min(a[1], b[1]) / c), math.floor(max(a[1], b[1]) / c) + 1):
                self.buckets.setdefault((bx, by), []).append(idx)
        return idx

    def add_polyline(self, pts, payload=None):
        for i in range(len(pts) - 1):
            self.add(pts[i], pts[i + 1], payload)

    def payload(self, idx):
        return self.segs[idx][4]

    def segment(self, idx):
        s = self.segs[idx]
        return (s[0], s[1]), (s[2], s[3])

    def candidates(self, x0, y0, x1, y1):
        c, seen = self.cell, set()
        for bx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for by in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for idx in self.buckets.get((bx, by), ()):
                    if idx not in seen:
                        seen.add(idx)
                        yield idx

    def nearest(self, x, y, maxd):
        best = None
        for idx in self.candidates(x - maxd, y - maxd, x + maxd, y + maxd):
            ax, ay, bx, by, _ = self.segs[idx]
            d, t = seg_point(x, y, ax, ay, bx, by)
            if d <= maxd and (best is None or d < best[0]):
                best = (d, idx, t)
        return best


def seg_intersect(a, b, c, d):
    rx, ry, sx, sy = b[0] - a[0], b[1] - a[1], d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t, u = (qx * sy - qy * sx) / den, (qx * ry - qy * rx) / den
    return (t, u) if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0 else None


def polyline_intersections(P, Q, merge_cm=100.0):
    """[(x, y, i, t, j, u)]: P's segment i at t crosses Q's segment j at u; hits closer than merge_cm are one."""
    idx = SegmentIndex(2000.0)
    for j in range(len(Q) - 1):
        idx.add(Q[j], Q[j + 1], j)
    out = []
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        for s in idx.candidates(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
            c, d = idx.segment(s)
            hit = seg_intersect(a, b, c, d)
            if hit is None:
                continue
            x, y = a[0] + (b[0] - a[0]) * hit[0], a[1] + (b[1] - a[1]) * hit[0]
            if all(math.hypot(x - o[0], y - o[1]) > merge_cm for o in out):
                out.append((x, y, i, hit[0], idx.payload(s), hit[1]))
    return out


def point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def rect(cx, cy, w, d, yaw):
    """The w x d rectangle centred on (cx, cy), w along the yaw direction, counter-clockwise."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    hw, hd = 0.5 * w, 0.5 * d
    return [(cx + c * a - s * b, cy + s * a + c * b) for a, b in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]


def circle(cx, cy, r, n=24):
    return [(cx + r * math.cos(2 * math.pi * q / n), cy + r * math.sin(2 * math.pi * q / n)) for q in range(n)]


def centroid(ring):
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def ring_distance(x, y, ring):
    n = len(ring)
    return min(seg_point(x, y, ring[i][0], ring[i][1], ring[(i + 1) % n][0], ring[(i + 1) % n][1])[0]
               for i in range(n))


def probe_points(ring, step):
    """The ring's boundary every `step` (corners included) and its centroid: what a plot checks for clearance."""
    out = [centroid(ring)]
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        m = max(1, int(math.ceil(dist2d(a, b) / step)))
        out.extend(lerp(a, b, q / m) for q in range(m))
    return out


def _bbox(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def rings_overlap(a, b):
    """Separating axis test for two convex rings."""
    for ring in (a, b):
        n = len(ring)
        for i in range(n):
            ex, ey = ring[(i + 1) % n][0] - ring[i][0], ring[(i + 1) % n][1] - ring[i][1]
            ax, ay = -ey, ex
            pa = [p[0] * ax + p[1] * ay for p in a]
            pb = [p[0] * ax + p[1] * ay for p in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


class RingIndex:
    """Convex rings bucketed by bounding box: containment, nearness and overlap queries."""

    def __init__(self, cell=3000.0):
        self.cell = float(cell)
        self.rings, self.payloads, self.boxes = [], [], []
        self.buckets = {}

    def add(self, ring, payload=None):
        idx = len(self.rings)
        self.rings.append(list(ring))
        self.payloads.append(payload)
        box = _bbox(ring)
        self.boxes.append(box)
        c = self.cell
        for bx in range(math.floor(box[0] / c), math.floor(box[2] / c) + 1):
            for by in range(math.floor(box[1] / c), math.floor(box[3] / c) + 1):
                self.buckets.setdefault((bx, by), []).append(idx)
        return idx

    def _cands(self, x0, y0, x1, y1):
        c, seen = self.cell, set()
        for bx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for by in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for idx in self.buckets.get((bx, by), ()):
                    if idx not in seen:
                        seen.add(idx)
                        yield idx

    def contains(self, x, y):
        for idx in self._cands(x, y, x, y):
            if point_in_ring(x, y, self.rings[idx]):
                p = self.payloads[idx]
                return True if p is None else p
        return None

    def near(self, x, y, margin):
        for idx in self._cands(x - margin, y - margin, x + margin, y + margin):
            ring = self.rings[idx]
            if point_in_ring(x, y, ring) or ring_distance(x, y, ring) <= margin:
                return True
        return False

    def overlaps(self, ring):
        x0, y0, x1, y1 = _bbox(ring)
        return any(rings_overlap(ring, self.rings[i]) for i in self._cands(x0, y0, x1, y1))
