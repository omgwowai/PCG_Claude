"""The engine's own arithmetic for the frames PCG data carries (pure; no unreal import).

Stage 11 hands the native building nodes footprints whose vertices went through two or three engine round
trips -- a polygon rebuilt by `CreatePolygon2D` (its plane frame, then the local 2D vertices), read back as
points (`UPCGPolygon2DData::GetTransformAtDistance`), and a closed spline sampled by distance
(`FDistanceStepSampler` over `FSplineCurves`' float reparam table). A downstream stage reads the last bits of
such geometry (traps.md 62), so each function below follows the C++ it names in operation order, in doubles
where the engine uses doubles and in float32 where it uses floats (`f32`).

  polygon_frame        `PolygonTriangulation::ComputePolygonPlane` (Newell) + `FRotationMatrix::MakeFromZ`
                       + `FQuat(FMatrix)`: the frame `CreatePolygon2D` / `MakePolygon2DData` give a ring
  to_local             `FTransform::InverseTransformPosition` (scale 1), dropping z: the stored 2D vertices
  vertex_points        `GetTransformAtDistance(i, 0, world)`: `FSegment2d::PointAt(-Extent)` then the frame
  rebuilt_vertices     the three above in a row (what `ToPoint` reads off a rebuilt polygon)
  SplineCurve          `FSplineCurves` (Hermite segments, the 10-step float reparam table) and
                       `FDistanceStepSampler` (`bFitToCurve`) on one spline
"""
import math
import struct

from .plane import quat_rotate


def f32(x):
    """Round a double to the nearest float32 (as a double): what a C++ `float` holds."""
    return struct.unpack("f", struct.pack("f", x))[0]


UP = (0.0, 0.0, 1.0)
KINDA_SMALL = 1.0e-4                    # UE_KINDA_SMALL_NUMBER
SMALL = 1.0e-8                          # UE_SMALL_NUMBER


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _size(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def safe_normal(v, tol=SMALL):
    """`FVector::GetSafeNormal`: v / |v| (via `InvSqrt` of the squared length), zero when too short."""
    sq = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
    if sq == 1.0:
        return tuple(v)
    if sq < tol:
        return (0.0, 0.0, 0.0)
    s = 1.0 / math.sqrt(sq)
    return (v[0] * s, v[1] * s, v[2] * s)


def _normalize_geometry(v):
    """`UE::Geometry::Normalize(TVector)`: returns (unit vector, length); length 0 -> zero vector."""
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length > 0.0:
        inv = 1.0 / length
        return (v[0] * inv, v[1] * inv, v[2] * inv), length
    return (0.0, 0.0, 0.0), 0.0


def quat_from_axes(x_axis, y_axis, z_axis):
    """`FQuat(const FMatrix&)` for a rotation matrix with rows X, Y, Z (UE's row-vector convention)."""
    m = (x_axis, y_axis, z_axis)
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0.0:
        inv_s = 1.0 / math.sqrt(tr + 1.0)
        w = 0.5 * (1.0 / inv_s)
        s = 0.5 * inv_s
        return ((m[1][2] - m[2][1]) * s, (m[2][0] - m[0][2]) * s, (m[0][1] - m[1][0]) * s, w)
    i = 0
    if m[1][1] > m[0][0]:
        i = 1
    if m[2][2] > m[i][i]:
        i = 2
    nxt = (1, 2, 0)
    j = nxt[i]
    k = nxt[j]
    s = m[i][i] - m[j][j] - m[k][k] + 1.0
    inv_s = 1.0 / math.sqrt(s)
    q = [0.0, 0.0, 0.0, 0.0]
    q[i] = 0.5 * (1.0 / inv_s)
    s = 0.5 * inv_s
    q[3] = (m[j][k] - m[k][j]) * s
    q[j] = (m[i][j] + m[j][i]) * s
    q[k] = (m[i][k] + m[k][i]) * s
    return tuple(q)


def make_from_z(z_axis):
    """`FRotationMatrix::MakeFromZ(Z).ToQuat()`."""
    new_z = safe_normal(z_axis)
    up = (0.0, 0.0, 1.0) if abs(new_z[2]) < (1.0 - KINDA_SMALL) else (1.0, 0.0, 0.0)
    new_x = safe_normal(_cross(up, new_z))
    new_y = _cross(new_z, new_x)
    return quat_from_axes(new_x, new_y, new_z)


def make_from_xz(x_axis, z_axis):
    """`FRotationMatrix::MakeFromXZ(X, Z).ToQuat()`."""
    new_x = safe_normal(x_axis)
    norm = safe_normal(z_axis)
    new_y = safe_normal(_cross(norm, new_x))
    new_z = _cross(new_x, new_y)
    return quat_from_axes(new_x, new_y, new_z)


def quat_mul(a, b):
    """`a * b` (Hamilton product, UE's `FQuat::operator*`): rotate by b, then by a."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def rotator_of(q):
    """`FQuat4d::Rotator()`: (pitch, yaw, roll) in degrees."""
    x, y, z, w = q
    sing = z * x - w * y
    yaw_y = 2.0 * (w * z + x * y)
    yaw_x = 1.0 - 2.0 * (y * y + z * z)
    rad = 180.0 / math.pi
    if sing < -0.4999995:
        return (-90.0, _normalize_axis(-2.0 * math.atan2(x, w) * rad), 0.0)
    if sing > 0.4999995:
        return (90.0, _normalize_axis(2.0 * math.atan2(x, w) * rad), 0.0)
    pitch = math.asin(2.0 * sing) * rad
    yaw = (math.atan2(yaw_y, yaw_x) if (yaw_y != 0.0 or yaw_x != 0.0) else 0.0) * rad
    roll_y, roll_x = -2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y)
    roll = (math.atan2(roll_y, roll_x) if (roll_y != 0.0 or roll_x != 0.0) else 0.0) * rad
    return (pitch, yaw, roll)


def _normalize_axis(a):
    a = math.fmod(a, 360.0)
    if a < 0.0:
        a += 360.0
    if a > 180.0:
        a -= 360.0
    return a


def _conj(q):
    return (-q[0], -q[1], -q[2], q[3])


# ---- polygons -------------------------------------------------------------------------------------
def polygon_plane(points):
    """`ComputePolygonPlane`: (unit normal, centroid, area) by Newell's method over 3D points."""
    nx = ny = nz = 0.0
    cx = cy = cz = 0.0
    n = len(points)
    i = n - 1
    for j in range(n):
        pi, pj = points[i], points[j]
        cx += pj[0]
        cy += pj[1]
        cz += pj[2]
        nx += (pj[1] - pi[1]) * (pi[2] + pj[2])
        ny += (pj[2] - pi[2]) * (pi[0] + pj[0])
        nz += (pj[0] - pi[0]) * (pi[1] + pj[1])
        i = j
    r = 1.0 / n                         # `TVector::operator/=` multiplies by the reciprocal
    centroid = (cx * r, cy * r, cz * r)
    normal, length = _normalize_geometry((nx, ny, nz))
    return normal, centroid, 0.5 * length


def polygon_frame(points):
    """The frame `CreatePolygon2D` gives a ring of 3D points: (translation, quaternion). A ring with no
    area keeps the up normal; a downward normal is flipped (`PyPCGToolsLibrary.cpp` MakePolygon2DData, which
    mirrors the engine element)."""
    normal, centroid, area = polygon_plane(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    if area <= SMALL * size * size:
        normal = UP
    if normal[0] * UP[0] + normal[1] * UP[1] + normal[2] * UP[2] < 0:
        normal = (-normal[0], -normal[1], -normal[2])
    return centroid, make_from_z(normal)


def to_local(points, t, q):
    """`FTransform::InverseTransformPosition` (scale 1) of each point, z dropped: the stored 2D vertices."""
    out = []
    qc = _conj(q)
    for p in points:
        v = quat_rotate(qc, (p[0] - t[0], p[1] - t[1], p[2] - t[2]))
        out.append((v[0], v[1]))
    return out


def signed_area_2d(ring):
    """`FPolygon2d::SignedArea`."""
    a = 0.0
    n = len(ring)
    for i in range(n):
        p, q = ring[i], ring[(i + 1) % n]
        a += p[0] * q[1] - p[1] * q[0]
    return a * 0.5


def segment_start(a, b):
    """`FSegment2d(a, b).PointAt(0 - Extent)`: the start point as the segment recomputes it."""
    cx, cy = 0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1])
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length > 0.0:
        inv = 1.0 / length
        dx, dy = dx * inv, dy * inv
        extent = 0.5 * length
    else:
        dx = dy = 0.0
        extent = 0.0
    s = 0.0 - extent
    return (cx + s * dx, cy + s * dy), (dx, dy)


def vertex_points(local, t, q):
    """`GetTransformAtDistance(i, 0, world)` for every vertex of a stored 2D ring: (positions, rotations).
    The rotation is the segment's `MakeFromXZ(direction, up)` composed with the frame (`OutTransform *
    Transform`: the frame's rotation applied after the segment's)."""
    pos, rot = [], []
    n = len(local)
    for i in range(n):
        (px, py), (dx, dy) = segment_start(local[i], local[(i + 1) % n])
        r = quat_rotate(q, (px, py, 0.0))
        pos.append((r[0] + t[0], r[1] + t[1], r[2] + t[2]))
        seg_q = (0.0, 0.0, 0.0, 1.0) if (abs(dx) <= SMALL and abs(dy) <= SMALL) else make_from_xz((dx, dy, 0.0), UP)
        rot.append(quat_mul(q, seg_q))
    return pos, rot


def rebuilt_vertices(points):
    """A ring of 3D points through `CreatePolygon2D` and back out as points: the frame, the stored local
    ring (reversed when clockwise, as the element does), then `vertex_points`. Returns (positions,
    rotations, frame) in the ring's order after the element's orientation fix."""
    t, q = polygon_frame(points)
    local = to_local(points, t, q)
    if signed_area_2d(local) < 0:
        local = local[::-1]
    pos, rot = vertex_points(local, t, q)
    return pos, rot, (t, q)


# ---- splines --------------------------------------------------------------------------------------
_LG = [(f32(0.0), f32(0.5688889)), (f32(-0.5384693), f32(0.47862867)), (f32(0.5384693), f32(0.47862867)),
       (f32(-0.90617985), f32(0.23692688)), (f32(0.90617985), f32(0.23692688))]
REPARAM_STEPS = 10                    # USplineComponent::ReparamStepsPerSegment's default


class SplineCurve:
    """One spline as `FSplineCurves` holds it: local control points (world less the data's translation,
    which is what the engine evaluates before adding it back), Hermite or linear segments, and the
    distance -> input key table in floats."""

    def __init__(self, points, arrive, leave, linear, closed, origin=(0.0, 0.0, 0.0)):
        self.origin = tuple(origin)
        self.p = [_sub(tuple(p), self.origin) for p in points]
        self.a = [tuple(x) for x in arrive]
        self.l = [tuple(x) for x in leave]
        self.linear = list(linear)
        self.closed = bool(closed)
        n = len(self.p)
        self.nseg = n if self.closed else max(0, n - 1)
        self.table = []
        acc = f32(0.0)
        for s in range(self.nseg):
            for step in range(REPARAM_STEPS):
                param = f32(f32(float(step)) / f32(float(REPARAM_STEPS)))
                seg = f32(0.0) if step == 0 else self.segment_length(s, param)
                self.table.append((f32(seg + acc), f32(s + param)))
            acc = f32(acc + self.segment_length(s, f32(1.0)))
        self.table.append((acc, f32(float(self.nseg))))

    @classmethod
    def of(cls, spline, origin=None):
        """From a `geo.Spline`: world control points, tangents (None for a linear spline: zero), and the
        data's own translation when `convert` recorded it (`Spline.frame`)."""
        n = len(spline.points)
        if spline.tangents:
            arrive = [t[0] for t in spline.tangents]
            leave = [t[1] for t in spline.tangents]
        else:
            arrive = leave = [(0.0, 0.0, 0.0)] * n
        if origin is None:
            frame = getattr(spline, "frame", None)
            origin = frame[0] if frame else (0.0, 0.0, 0.0)
        return cls(spline.points, arrive, leave, [bool(spline.linear)] * n, spline.closed, origin)

    def segment_length(self, i, param):
        """`FSplineCurves::GetSegmentLength` (5-point Legendre-Gauss in floats over double derivatives)."""
        n = len(self.p)
        j = 0 if i == n - 1 else i + 1
        p0, t0, p1, t1 = self.p[i], self.l[i], self.p[j], self.a[j]
        if self.linear[i]:
            return f32(_size(_sub(p1, p0)) * param)
        c1 = _mul(_add(_add(_mul(_sub(p0, p1), 2.0), t0), t1), 3.0)
        c2 = _sub(_sub(_mul(_sub(p1, p0), 6.0), _mul(t0, 4.0)), _mul(t1, 2.0))
        half = f32(param * f32(0.5))
        length = f32(0.0)
        for absc, w in _LG:
            alpha = f32(half * f32(f32(1.0) + absc))
            d = _add(_mul(_add(_mul(c1, alpha), c2), alpha), t0)
            length = f32(length + _size(d) * w)
        return f32(length * half)

    def length(self):
        return self.table[-1][0]

    def distance_at_point(self, k):
        return self.length() if (self.closed and k == self.nseg) else self.table[k * REPARAM_STEPS][0]

    def key_at(self, distance):
        """`ReparamTable.Eval(Distance)`: the float table, linearly interpolated in floats."""
        x = f32(distance)
        t = self.table
        if x < t[0][0]:
            return t[0][1]
        if x >= t[-1][0]:
            return t[-1][1]
        lo, hi = 0, len(t) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if t[mid][0] <= x:
                lo = mid
            else:
                hi = mid
        a, b = t[lo], t[lo + 1]
        diff = f32(b[0] - a[0])
        if diff > 0.0:
            alpha = f32(f32(x - a[0]) / diff)
            return f32(a[1] + f32(alpha * f32(b[1] - a[1])))
        return a[1]

    def local_at_key(self, key):
        """`Position.Eval(key)` (`FInterpCurve::Eval` with `FMath::CubicInterp` in floats for the weights)."""
        n = len(self.p)
        if key < 0.0:
            return self.p[0]
        i = int(math.floor(key))
        if i >= n - 1 and not self.closed:
            return self.p[-1]
        if i >= n:
            return self.p[0]
        j = 0 if i == n - 1 else i + 1
        a = f32(key - f32(float(i)))
        if self.linear[i]:
            return _add(self.p[i], _mul(_sub(self.p[j], self.p[i]), a))
        a2 = f32(a * a)
        a3 = f32(a2 * a)
        c0 = f32(f32(f32(2.0 * a3) - f32(3.0 * a2)) + 1.0)
        c1 = f32(f32(a3 - f32(2.0 * a2)) + a)
        c2 = f32(a3 - a2)
        c3 = f32(f32(-2.0 * a3) + f32(3.0 * a2))
        return _add(_add(_add(_mul(self.p[i], c0), _mul(self.l[i], c1)), _mul(self.a[j], c2)), _mul(self.p[j], c3))

    def sample_distance(self, increment):
        """`FDistanceStepSampler` with `bFitToCurve` (no offsets, no jitter): world positions."""
        total = self.length()
        num = int(total / increment) if increment > 0 else 0
        step = total / (num if self.closed else max(1, num - 1)) if num > 0 else increment
        out = []
        cur, seg, start, count = 0.0, 0, 0.0, 0

        def seg_len(s):
            return self.distance_at_point(s + 1) - self.distance_at_point(s)

        def done():
            return (start + cur > total + SMALL) or count == num

        while not done() and self.nseg > 0:
            if seg >= self.nseg:
                seg = self.nseg - 1
                cur = seg_len(seg)
                start = self.distance_at_point(seg)
            key = self.key_at(self.distance_at_point(seg) + cur)
            out.append(_add(self.local_at_key(key), self.origin))
            length = seg_len(seg)
            cur += step
            count += 1
            while cur > length:
                cur -= length
                seg += 1
                start += length
                if done() or length <= 0:
                    break
                length = seg_len(seg)
        return out

    def at_distance(self, distance):
        """`GetLocationAtDistanceAlongSpline(Distance, World)`."""
        return _add(self.local_at_key(self.key_at(distance)), self.origin)

    def polyline(self):
        """`FPCGSplineStruct::ConvertSplineToPolyLine` for a spline whose segments are all linear (a curved
        segment raises): a zero-length segment gives its stop point alone, each later segment replaces the
        previous last point with its own start."""
        out = []
        for s in range(self.nseg):
            if not self.linear[s]:
                raise ValueError("polyline() handles linear segments only")
            start, stop = self.distance_at_point(s), self.distance_at_point(s + 1)
            seg = [self.at_distance(stop)] if stop - start == 0.0 else [self.at_distance(start), self.at_distance(stop)]
            if out:
                out.pop()
            out += seg
        return out


def create_polygon_points(curve):
    """The 3D points `CreatePolygon2D` reads off a closed spline: its polyline, the closing point popped."""
    pts = curve.polyline()
    if curve.closed and pts:
        pts.pop()
    return pts


# ---- Transform_Align and Transform_Offset on closed splines (stage 15 first) -----------------------
def world_box(points):
    """`([min], [max])` over a closed spline's control points: what `CombinePoints`
    (`bUseFirstPointTransform` false) reports for an item -- every point's box in the data's own frame,
    which for a spline read back from the engine has an identity rotation. `None` for no points."""
    if not points:
        return None
    return ([min(p[a] for p in points) for a in range(3)], [max(p[a] for p in points) for a in range(3)])


def box_centre(points):
    """The centre of `world_box`: `(min + max) / 2`, which is what a `Justify_* = Center` reads."""
    b = world_box(points)
    if b is None:
        return None
    return tuple(0.5 * (b[0][a] + b[1][a]) for a in range(3))


def align(points, target):
    """`Transform_Align` with `Justify_X/Y = Center -> Same` and `Justify_Z = None`: every point moved by
    the difference between the SECOND input's box centre (`target`: the (min, max) box, or a centre
    triple) and the first's. The move is a world translation, applied to the control points; the
    primitive rebuilds the polygon from the moved points, which is the same ring.

    Measured on stage 15 (2026-10-20, `Saved/t22/tap15_a.json`): the three arm alignments and the inner
    ring's are exactly this shift, to 1e-12 cm, with Z untouched (its `Justify_Z` is None)."""
    c = box_centre(points)
    if target is None:
        return [tuple(p) for p in points]
    t = box_centre(target) if (len(target) == 2 and isinstance(target[0], (list, tuple))) else tuple(target)
    if c is None or t is None:
        return [tuple(p) for p in points]
    d = (t[0] - c[0], t[1] - c[1])
    return [(p[0] + d[0], p[1] + d[1], p[2]) for p in points]


def rotate_in_frame(points, yaw_deg, origin):
    """`Transform_Offset` with `PerPoints` FALSE and a yaw-only `rotationOffset`: the primitive inverts
    the data's own transform, rotates the control points as they stand in that frame (about the frame's
    ORIGIN), and transforms back. With a frame whose rotation is identity -- every piece of stage 15's
    chain carries one -- that is a rotation about `origin`, the frame's translation:

        world' = origin + q_yaw (p - origin)

    Measured 2026-10-20 on stage 15: the -60 deg base rotation and both +-120 deg arm rotations are this
    map about (-613.8667464186474, 142.0539320733078), to 1e-12 cm on every vertex (`tap15_a.json`,
    `s15.md` section 5). The Z of `origin` does not matter for a yaw."""
    ox, oy = float(origin[0]), float(origin[1])
    q = (0.0, 0.0, math.sin(math.radians(yaw_deg) * 0.5), math.cos(math.radians(yaw_deg) * 0.5))
    out = []
    for p in points:
        v = quat_rotate(q, (p[0] - ox, p[1] - oy, 0.0))
        out.append((ox + v[0], oy + v[1], p[2]))
    return out


def spline_of(polygon):
    """A ring as the closed linear spline `PrepareOutputs_ClosedSplinesAndSplines` publishes: the polygon's
    outer vertices (its `ToPoint` reads, z included, one z per vertex) at the polygon's own rotation
    (`Polygon.frame`), not the centroid. `Polygon.vertices` when `convert` filled them, else `outer`."""
    pts = list(polygon.vertices) if polygon.vertices else [(p[0], p[1], polygon.z) for p in polygon.outer]
    if polygon.zs is not None and polygon.vertices is None and len(polygon.zs) == len(pts):
        pts = [(p[0], p[1], z) for p, z in zip(pts, polygon.zs)]
    return pts


class SplinePolygon:
    """A closed linear spline as `CreatePolygon2D` makes it into a polygon (the `InputsProcessing_ForcePolygon` of
    every area primitive), and that polygon read back out (stage 12):

      points    the 3D points the element reads (`create_polygon_points`)
      frame     (translation, quaternion): `polygon_frame`
      local     the stored 2D ring, counter-clockwise (reversed when the points run clockwise, as the element does)
      area      `@data.$area`: the stored ring's area, cm2
      vertices  `ToPoint` / `GetSplineControlPoints` on the polygon (`vertex_points`), in the stored ring's order
      rotations their rotations
    """

    def __init__(self, spline):
        self._init(SplineCurve.of(spline))

    @classmethod
    def of_curve(cls, curve):
        """The same polygon from a `SplineCurve` whose points already carry their own z (a closed spline read
        back from the engine, which a stage has edited point by point)."""
        out = cls.__new__(cls)
        out._init(curve)
        return out

    def _init(self, curve):
        self.points = create_polygon_points(curve)
        self.frame = polygon_frame(self.points)
        t, q = self.frame
        local = to_local(self.points, t, q)
        if signed_area_2d(local) < 0:
            local = local[::-1]
        self.local = local
        self.area = abs(signed_area_2d(local))
        self.vertices, self.rotations = vertex_points(local, t, q)


def polygon_of(points):
    """`CreatePolygon2D` on a closed linear spline read back from the engine: the stored ring, its area and
    the vertices `ToPoint` reads (`rebuilt_vertices`), as (Polygon, SplinePolygon)."""
    from .types import Polygon
    n = len(points)
    curve = SplineCurve(points, [(0.0, 0.0, 0.0)] * n, [(0.0, 0.0, 0.0)] * n, [True] * n, True)
    sp = SplinePolygon.of_curve(curve)
    return Polygon([(p[0], p[1]) for p in sp.vertices], [], sp.vertices[0][2] if sp.vertices else 0.0,
                   zs=[p[2] for p in sp.vertices]), sp
