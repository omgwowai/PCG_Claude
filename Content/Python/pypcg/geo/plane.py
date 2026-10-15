"""Pure 2D geometry on (x, y) tuples in cm (promoted from the Districts spike, 2026-10-15)."""
import bisect
import math


def signed_area(p):
    return 0.5 * sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p)))


def ccw(p):
    """CreatePolygon2D forces the outer ring counter-clockwise (positive shoelace area)."""
    return list(p) if signed_area(p) >= 0 else list(reversed(p))


def bbox(pts):
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return (min(xs), min(ys)), (max(xs), max(ys))


def unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-12 else (0.0, 0.0)


def inside(pt, ring):
    x, y, c, j = pt[0], pt[1], False, len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i][:2], ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def path_length(path):
    return sum(math.dist(path[i][:2], path[i + 1][:2]) for i in range(len(path) - 1))


def drop_closing(points):
    """A closed polyline as the engine samples it repeats its first vertex at the end; drop it."""
    return list(points[:-1]) if len(points) > 1 and math.dist(points[0], points[-1]) < 1e-6 else list(points)


def xy(points):
    return [(p[0], p[1]) for p in points]


def rotate(p, yaw_deg):
    r = math.radians(yaw_deg)
    return (p[0] * math.cos(r) - p[1] * math.sin(r), p[0] * math.sin(r) + p[1] * math.cos(r))


def ngon(center, radius, n, start_deg=0.0, step_deg=None, y_scale=1.0, yaw_deg=0.0):
    """Create_Spline_Shape's polygon: n points on a circle of `radius`, the first at start_deg,
    stepping step_deg (default 360/n), stretched by y_scale along local Y, turned by yaw_deg."""
    step = 360.0 / n if step_deg is None else step_deg
    out = []
    for k in range(n):
        a = math.radians(start_deg + k * step)
        x, y = rotate((radius * math.cos(a), radius * y_scale * math.sin(a)), yaw_deg)
        out.append((center[0] + x, center[1] + y))
    return out


def rect(center, half_x, half_y, yaw_deg=0.0, order=((-1, 1), (1, 1), (1, -1), (-1, -1))):
    """Create_Spline_Shape's 4-gon (grid corners + convex hull): corners in the official order."""
    out = []
    for sx, sy in order:
        x, y = rotate((sx * half_x, sy * half_y), yaw_deg)
        out.append((center[0] + x, center[1] + y))
    return out


# ---- Polygon2DOperation(CutWithPaths): GetEnclosingPolygonFromPath ------------------------
def enclosing_polygon(path, bb):
    """Close an open path around the polygon's box (expanded by 1 %) on its left side."""
    (x0, y0), (x1, y1) = bb
    pad = max(1.0, 0.01 * max(x1 - x0, y1 - y0))
    targets = [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad), tuple(path[0])]
    out = [tuple(q) for q in path]
    while True:
        (ax, ay), (bx, by) = out[-2], out[-1]
        dx, dy = unit(bx - ax, by - ay)
        best, best_a = 0, None
        for k, (tx, ty) in enumerate(targets):
            ux, uy = unit(tx - bx, ty - by)
            a = math.atan2(dx * uy - dy * ux, ux * dx + uy * dy) % (2 * math.pi)
            if best_a is None or a < best_a:
                best, best_a = k, a
        if best == len(targets) - 1:
            return out
        out.append(targets.pop(best))


# ---- ClipPaths(Intersection): the parts of an open path inside a ring ----------------------
def _at(path, cum, s):
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    return (path[i][0] + t * (path[i + 1][0] - path[i][0]), path[i][1] + t * (path[i + 1][1] - path[i][1]))


def clip_path(path, ring):
    n = len(ring)
    edges = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        edges.append((a, b, min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])))
    cum = [0.0]
    for i in range(len(path) - 1):
        cum.append(cum[-1] + math.dist(path[i][:2], path[i + 1][:2]))
    cuts = []
    for i in range(len(path) - 1):
        p, q = path[i], path[i + 1]
        sx0, sx1, sy0, sy1 = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
        rx, ry = q[0] - p[0], q[1] - p[1]
        for a, b, ex0, ex1, ey0, ey1 in edges:
            if ex1 < sx0 or ex0 > sx1 or ey1 < sy0 or ey0 > sy1:
                continue
            sx, sy = b[0] - a[0], b[1] - a[1]
            den = rx * sy - ry * sx
            if den == 0:
                continue
            wx, wy = a[0] - p[0], a[1] - p[1]
            t, u = (wx * sy - wy * sx) / den, (wx * ry - wy * rx) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u < 1.0:
                cuts.append(cum[i] + t * (cum[i + 1] - cum[i]))
    marks, spans = [0.0] + sorted(cuts) + [cum[-1]], []
    for s0, s1 in zip(marks, marks[1:]):
        if s1 - s0 > 1e-6 and inside(_at(path, cum, 0.5 * (s0 + s1)), ring):
            if spans and abs(spans[-1][1] - s0) < 1e-6:
                spans[-1][1] = s1
            else:
                spans.append([s0, s1])
    return [[_at(path, cum, s0)] + [tuple(path[k][:2]) for k in range(bisect.bisect_right(cum, s0), bisect.bisect_left(cum, s1))]
            + [_at(path, cum, s1)] for s0, s1 in spans]


# ---- CleanSpline (5 deg collinear, open curve spline, auto tangents) ----------------------
def clean_points(pts, angle_deg=5.0):
    n = len(pts)

    def tan(i):                       # CurveAuto tangent direction: next - previous, clamped at the ends
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        return (b[0] - a[0], b[1] - a[1])

    thr = max(abs(math.cos(math.radians(angle_deg))), 1e-8)

    def col(v, w):
        a, b = math.hypot(*v), math.hypot(*w)
        return a > 0 and b > 0 and abs((v[0] * w[0] + v[1] * w[1]) / (a * b)) >= thr

    cp = [[tuple(pts[i]), tan(i), tan(i)] for i in range(n)]       # position, arrive, leave
    k = len(cp) - 1
    while k >= 2:                     # reverse triplet scan, as FPCGCleanSplineElement does
        s, p, c = cp[k - 2], cp[k - 1], cp[k]
        seg = (c[0][0] - s[0][0], c[0][1] - s[0][1])
        if col(s[2], seg) and col(p[1], seg) and col(p[2], seg) and col(c[1], seg):
            s[2] = c[1] = seg
            del cp[k - 1]
        k -= 1
    return [q[0] for q in cp]


# ---- the longest-edge frame + CombinePoints bounds ----------------------------------------
def longest(ring):
    n = len(ring)
    return max(range(n), key=lambda i: math.dist(ring[i], ring[(i + 1) % n]))


def frame_box(ring):
    """Frame at the longest outer edge's start vertex (X along the edge, Y its left normal) and the
    bounds of every vertex point (+-1 cm boxes turned with their segment) in that frame."""
    n, k = len(ring), longest(ring)
    o = ring[k]
    X = unit(ring[(k + 1) % n][0] - o[0], ring[(k + 1) % n][1] - o[1])
    Y = (-X[1], X[0])
    us, ws = [], []
    for i, q in enumerate(ring):
        d = unit(ring[(i + 1) % n][0] - q[0], ring[(i + 1) % n][1] - q[1])
        e = abs(d[0] * X[0] + d[1] * X[1]) + abs(d[0] * Y[0] + d[1] * Y[1])
        u = (q[0] - o[0]) * X[0] + (q[1] - o[1]) * X[1]
        w = (q[0] - o[0]) * Y[0] + (q[1] - o[1]) * Y[1]
        us += [u - e, u + e]
        ws += [w - e, w + e]
    return o, X, Y, min(us), max(us), min(ws), max(ws)


def at(o, X, Y, u, w):
    return (o[0] + X[0] * u + Y[0] * w, o[1] + X[1] * u + Y[1] * w)


def split_frame(ring):
    """AutoSplitPolygon's frame: CleanSpline the ring, force it counter-clockwise, then frame_box."""
    return frame_box(ccw(clean_points(ring)))
