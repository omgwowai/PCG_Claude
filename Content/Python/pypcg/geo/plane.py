"""Pure 2D geometry on (x, y) tuples in cm (promoted from the Districts spike, 2026-10-15)."""
import bisect
import math


def signed_area(p):
    return 0.5 * sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p)))


def ccw(p):
    """CreatePolygon2D forces the outer ring counter-clockwise (positive shoelace area)."""
    return list(p) if signed_area(p) >= 0 else list(reversed(p))


def degenerate(ring, min_area_cm2=1.0):
    """A ring that encloses nothing: fewer than 3 distinct XY vertices, or under `min_area_cm2` of area.
    The engine's own booleans can hand such slivers back as holes (stage 7's planar union in the town,
    Task 27: a 3-vertex hole with two coincident points); `FGeneralPolygon2d::AddHole`'s containment check
    refuses them, though they remove no area."""
    distinct = {(float(v[0]), float(v[1])) for v in ring}
    return len(distinct) < 3 or abs(signed_area(ring)) < min_area_cm2


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


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def quat_rotate(q, v):
    """`FQuat::RotateVector` in UE's own operation order (`VectorQuaternionRotateVector`, no FMA):
    T = 2 (q.xyz x v); v' = (v + w T) + (q.xyz x T). q is (x, y, z, w), v is (x, y, z). Measured
    2026-10-19: with the stage-5 volume's own quaternion this reproduces all eight official park
    coordinates bit for bit, where a cos/sin rotation by the yaw is ~1e-11 cm off -- and downstream
    stages read those bits (stage 15 for stage 4)."""
    Q, w = q[:3], q[3]
    t = _cross(Q, v)
    t = (t[0] + t[0], t[1] + t[1], t[2] + t[2])
    c = _cross(Q, t)
    return (w * t[0] + v[0] + c[0], w * t[1] + v[1] + c[1], w * t[2] + v[2] + c[2])


def quat_from_yaw(yaw_deg):
    """A yaw-only quaternion, for callers that have no engine quaternion (offline tests). NOT
    bit-identical to an actor's stored quaternion: carry `Points.quat` through when you have it."""
    h = math.radians(yaw_deg) / 2.0
    return (0.0, 0.0, math.sin(h), math.cos(h))


def place(local, quat, loc):
    """`AttributeTransformOp_2`'s composition of local (x, y) points with the volume transform
    (scale 1): rotate by the quaternion, then add the translation -- in that order, in doubles. With
    the identity quaternion the rotation is exact, so a volume at yaw 0 adds only the translation."""
    out = []
    for x, y in local:
        r = quat_rotate(quat, (x, y, 0.0))
        out.append((r[0] + loc[0], r[1] + loc[1]))
    return out


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
def _at(path, cum, s, z=None):
    """The point at arclength `s` on `path`, interpolated. `z` is carried only when given, so a 2D
    path yields 2D points and a 3D one keeps its Z."""
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    x = path[i][0] + t * (path[i + 1][0] - path[i][0])
    y = path[i][1] + t * (path[i + 1][1] - path[i][1])
    return (x, y) if z is None else (x, y, z)


def clip_path(path, ring, keep_inside=True):
    """`ClipPaths(Intersection)` when `keep_inside`, `ClipPaths(Difference)` when not: the parts of
    an open path that lie inside (respectively outside) a ring.

    Both operations are the same walk -- cut the path at every crossing, then decide each span by
    testing its midpoint -- so one implementation serves them; PCG's `Compose_Spline_Cut` wires both
    (`ClipPaths_0` and `ClipPaths_1`) off the same `Branch_0`, and stage 7 uses each: the landmark
    clips and the intersection cutter remove (`Difference`), the "intersections" tag keeps
    (`DifferenceOrIntersection = true`)."""
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
        if s1 - s0 > 1e-6 and inside(_at(path, cum, 0.5 * (s0 + s1)), ring) == keep_inside:
            if spans and abs(spans[-1][1] - s0) < 1e-6:
                spans[-1][1] = s1
            else:
                spans.append([s0, s1])
    # The Z of each surviving vertex is carried through, but ONLY when the input carried one:
    # ClipPaths preserves the input's Z, and the road graph's own `Transform_Splines_Extend` and
    # `Transform_Offset` read it again afterwards. A 2D caller keeps 2D points -- stage 6 does, and
    # so does every caller that only ever wanted the cut piece's XY.
    pts = [tuple(p[:3]) for p in path] if len(path[0]) > 2 else [tuple(p[:2]) for p in path]
    return [[_at(path, cum, s0) if len(path[0]) <= 2 else _at(path, cum, s0, _z(path))]
            + [pts[k] for k in range(bisect.bisect_right(cum, s0), bisect.bisect_left(cum, s1))]
            + [_at(path, cum, s1) if len(path[0]) <= 2 else _at(path, cum, s1, _z(path))]
            for s0, s1 in spans]


def _z(path):
    """A path's third coordinate: its first point's, or 0 when the points are 2D."""
    return path[0][2] if len(path[0]) > 2 else 0.0



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


# ---- Extract_Segments (SplitSplines ByPredicateOnControlPoints) -----------------------------
def extract_segments(ring, angle_deg):
    """`Extract_Segments`: split a closed spline at every control point whose turn is over
    `angle_deg`, into the straight runs between those points.

    The CoreProcess (`Extract_Segments_CoreProcess`, 20 nodes) is:

      Splines_CalculateAngleToNextPoint   per control point, the angle to the next (subgraph)
      MetadataMaths(Divide)               that angle / CutAngleThreshold
      AttributeCast(Integer32)            truncated to an int
      SplitSplines(ByPredicateOnControlPoints, Attribute "predicate")
                                          split where the predicate holds

    The predicate's attribute is `$Index`, so a control point splits when its own index exceeds
    `angle/threshold` -- and since the points arrive in index order, "index > angle/threshold" is
    true from the first point on with a larger angle than the threshold. The set of split points is
    therefore exactly the control points whose angle to the next exceeds `angle_deg`, and the output
    is the runs between them. `CutAngleThreshold = 3` in stage 7's `Subgraph_3 Extract Road
    Segments`, whose input is the Landmarks ring.

    A segment is open and linear: `SplitSplines` slices the spline's control points, and the
    primitive rebuilds each run as a linear open spline."""
    pts = list(ring)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return [pts + [pts[0]]] if n == 2 else ([[pts[0]]] if n == 1 else [])
    cuts = []
    for i in range(n):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        u = unit(b[0] - a[0], b[1] - a[1])
        v = unit(c[0] - b[0], c[1] - b[1])
        ang = math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))
        if ang > float(angle_deg):
            cuts.append(i)
    if not cuts:
        return [pts + [pts[0]]]
    out = []
    for k, start in enumerate(cuts):
        end = cuts[(k + 1) % len(cuts)]
        run = []
        i = start
        while True:
            run.append(pts[i])
            i = (i + 1) % n
            if i == end:
                break
        run.append(pts[end])
        if len(run) >= 2:
            out.append(run)
    return out


# ---- ConvexHull2D: Andrew's monotone chain, as the engine runs it ---------------------------
def convex_hull(points):
    """Indices of the 2D convex hull of `points` (each `(x, y, ...)`), in the order
    `PCGConvexHull2D` outputs them.

    This is `ConvexHull2D::ComputeConvexHull` (Engine/Source/Runtime/Core/Public/Math/ConvexHull2d.h),
    which `FPCGConvexHull2DElement` calls on the points' locations (Z ignored):
      - three points or fewer come back as they are, in input order;
      - otherwise the indices are sorted by X, then Y (`Algo::Sort` is not stable, so the engine's
        order between EXACT duplicates is unspecified; Python's sort keeps input order); the lower hull is built left to right and the upper hull right to left, popping
        while the turn is clockwise OR COLLINEAR (`<= 0`), so collinear points are dropped and the
        result runs counter-clockwise from the lowest-X (then lowest-Y) point; the last index (the
        start again) is cut off.
    Measured 2026-10-19 on stage 17's 100 666 above-sea terrain points: the same 57 indices in the same
    order as the official node."""
    n = len(points)
    if n <= 3:
        return list(range(n))
    order = sorted(range(n), key=lambda i: (points[i][0], points[i][1]))

    def clockwise(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]) <= 0

    out = []
    for i in order:
        while len(out) >= 2 and clockwise(points[out[-2]], points[out[-1]], points[i]):
            out.pop()
        out.append(i)
    start = len(out) + 1
    for k in range(n - 1, 0, -1):
        i = order[k - 1]
        while len(out) >= start and clockwise(points[out[-2]], points[out[-1]], points[i]):
            out.pop()
        out.append(i)
    return out[:-1]


# ---- the longest-edge frame + CombinePoints bounds ----------------------------------------
def longest(ring):
    n = len(ring)
    return max(range(n), key=lambda i: math.dist(ring[i], ring[(i + 1) % n]))


def frame_box(ring, edge=None):
    """Frame at the longest outer edge's start vertex (X along the edge, Y its left normal) and the
    bounds of every vertex point (+-1 cm boxes turned with their segment) in that frame. `edge` names
    the frame's edge instead, for a ring whose edges tie and whose winner the engine's last bits decide
    (stage 15's regular hexagons)."""
    n = len(ring)
    k = longest(ring) if edge is None else int(edge) % n
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
