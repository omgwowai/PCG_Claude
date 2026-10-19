"""Ground-tile geometry (stage 10 first): the uniform tile grid of `Fill_Areas_Uniformly` and the
terrain fit of `Custom_Projector_with_rotation_fix`, as plain values. No unreal import.

Both primitives are read from their own graphs (exported 2026-10-19 under `Saved/graph_dumps/t17/`)
and the engine source they call; the docstring on each function names the nodes it stands for.

`fill_uniform`   `Fill_Areas_Uniformly` -> `Fill_Areas_Uniformly_CoreProcess` (53 nodes)
`project_tile`   `/CitySamplePCG/PCG/Custom_Projector_with_rotation_fix` (32 nodes)
`rot_from_xy`    `PCGMetadataMakeRotator(MakeRotFromXY)` = `FRotationMatrix::MakeFromXY(X, Y).Rotator()`
"""
import math

from .assets import _quat_of_matrix, quat_of
from .plane import quat_rotate

TILE_SPACING_FACTOR = 2.0          # the sampler's cell is 2 x PointExtents (Looseness 0)


# ---- the frame of a polygon's longest outer segment ---------------------------------------------
def longest_segment(ring):
    """`@Data.$LongestOuterSegmentIndex` (`PCGPolygon2DAccessor.h:253-269`): the FIRST outer segment of
    the greatest length, segment i running from vertex i to vertex i+1 (wrapping)."""
    best, best_len = -1, -float("inf")
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > best_len:
            best, best_len = i, d
    return best


def segment_quat(ring, i):
    """The control point's rotation at the start of segment i of a polygon (`GetSplineControlPoints` on
    a `Polygon2D`, `PCGPolygon2DAccessor.h:64-69`): `FRotationMatrix::MakeFromXZ(Direction, Up).ToQuat()`
    with `Direction` the segment's unit 2D direction -- a yaw-only frame. Returned as (x, y, z, w)."""
    n = len(ring)
    a, b = ring[i], ring[(i + 1) % n]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    dx, dy = dx / length, dy / length
    # MakeFromXZ(X, Z=Up): NewZ = Up, NewY = Z ^ X, NewX = NewY ^ NewZ (rows are the axes).
    x_axis = (dx, dy, 0.0)
    z_axis = (0.0, 0.0, 1.0)
    y_axis = (z_axis[1] * x_axis[2] - z_axis[2] * x_axis[1], z_axis[2] * x_axis[0] - z_axis[0] * x_axis[2],
              z_axis[0] * x_axis[1] - z_axis[1] * x_axis[0])
    return _quat_of_matrix([list(x_axis), list(y_axis), list(z_axis)])


def _conj(q):
    return (-q[0], -q[1], -q[2], q[3])


def yaw_of_quat(q):
    """`FQuat::Rotator()`'s yaw (degrees) of a yaw-only quaternion; pitch and roll are 0 exactly."""
    x, y, z, w = q
    return math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


# ---- Fill_Areas_Uniformly --------------------------------------------------------------------------
def fill_uniform(ring, z, extent):
    """`Fill_Areas_Uniformly` on ONE polygon (its outer ring, counter-clockwise; holes are not read --
    `GetSplineControlPoints_0` -> `CreateSpline_0` makes one closed spline of the outer vertices).

    The CoreProcess, node by node:

      CopyAttributes_1/2/3, GetSplineControlPoints_1, AttributeFilter_1
                       the control point at the start of the LONGEST outer segment; its `$Transform`
                       (a yaw-only frame, `segment_quat`) becomes `PointTransform`
      GetSplineControlPoints_0, AttributeVectorOp_1 (InverseTransformDirection)
                       every vertex into that frame -- a rotation about the WORLD origin, no translation
      CreateSpline_0 (closed, linear) -> CreateSurfaceFromSpline_0 -> SurfaceSampler_0
                       `PointExtents` = (e, e, e), `Looseness` 0, `bUnbounded`: the cell is 2e, no jitter,
                       one point at (i * 2e, j * 2e) for every integer i, j with
                       `CeilToInt((min - 1) / 2e) <= i <= FloorToInt((max + 1) / 2e)` (the spline's
                       bounds grow by its points' scale, 1 cm) that `FPolygon2d::Contains` puts inside
                       (`PCGSurfaceSampler.cpp:117-120, 276-296`; `PCGSplineInteriorSurfaceData.cpp:202`)
      AttributeVectorOp_0 (TransformDirection), CopyAttributes_5, AttributeMathsOp_1
                       back into the world; `$Rotation` = the frame (roll zeroed: it is yaw only)

    Returns `(locs, yaw)`: the world locations in the sampler's order (row j, then column i) and the
    frame's yaw in degrees, which is every point's `$Rotation`. The z of every point is the polygon's
    (the interior surface's height, `ProjectOntoSplineInteriorSurface`, of a flat ring)."""
    n = len(ring)
    if n < 3:
        return [], 0.0
    q = segment_quat(ring, longest_segment(ring))
    inv = _conj(q)
    local = []
    for p in ring:
        v = quat_rotate(inv, (float(p[0]), float(p[1]), float(z)))
        local.append((v[0], v[1]))
    cell = TILE_SPACING_FACTOR * float(extent)
    xs, ys = [p[0] for p in local], [p[1] for p in local]
    i0, i1 = math.ceil((min(xs) - 1.0) / cell), math.floor((max(xs) + 1.0) / cell)
    j0, j1 = math.ceil((min(ys) - 1.0) / cell), math.floor((max(ys) + 1.0) / cell)
    out = []
    for j in range(j0, j1 + 1):
        y = j * cell
        crossings = []
        for k in range(n):
            a, b = local[k], local[(k + 1) % n]
            if a[1] <= y < b[1]:
                up = 1
            elif b[1] <= y < a[1]:
                up = -1
            else:
                continue
            xc = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            crossings.append((xc, up))
        if not crossings:
            continue
        crossings.sort()
        # FPolygon2d::Contains: the winding number of the crossings strictly to the point's right, so a
        # point x is in span [xs[k-1], xs[k]) with the winding of crossings k.. -- swept once per row.
        suffix = [0] * (len(crossings) + 1)
        for k in range(len(crossings) - 1, -1, -1):
            suffix[k] = suffix[k + 1] + crossings[k][1]
        for k in range(1, len(crossings)):
            if suffix[k] == 0:
                continue
            lo, hi = crossings[k - 1][0], crossings[k][0]
            i = max(i0, math.ceil(lo / cell) - 1)
            while i * cell < lo:
                i += 1
            while i <= i1 and i * cell < hi:
                out.append(quat_rotate(q, (i * cell, y, float(z))))
                i += 1
    return out, yaw_of_quat(q)


# ---- Custom_Projector_with_rotation_fix -----------------------------------------------------------
def _safe_normal(v):
    s = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
    if s == 1.0:
        return v
    if s < 1e-8:
        return (0.0, 0.0, 0.0)
    f = 1.0 / math.sqrt(s)
    return (v[0] * f, v[1] * f, v[2] * f)


def _xp(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def rot_from_xy(x_axis, y_axis):
    """`MakeRotFromXY`: `FRotationMatrix::MakeFromXY(X, Y)` then `FMatrix::Rotator()`, as (pitch, yaw,
    roll) in degrees."""
    nx = _safe_normal(x_axis)
    norm = _safe_normal(y_axis)
    if abs(abs(_dot(nx, norm)) - 1.0) <= 1e-8:
        norm = (0.0, 0.0, 1.0) if abs(nx[2]) < (1.0 - 1e-4) else (1.0, 0.0, 0.0)
    nz = _safe_normal(_xp(nx, norm))
    ny = _xp(nz, nx)
    r2d = 180.0 / math.pi
    pitch = math.atan2(nx[2], math.sqrt(nx[0] * nx[0] + nx[1] * nx[1])) * r2d
    yaw = math.atan2(nx[1], nx[0]) * r2d
    # FRotationMatrix(pitch, yaw, 0)'s Y axis is (-sin yaw, cos yaw, 0).
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sya = (-sy, cy, 0.0)
    roll = math.atan2(_dot(nz, sya), _dot(ny, sya)) * r2d
    return (pitch, yaw, roll)


# The three corners `ResetPointCenter_0/1/2` move a point to: (min x, min y), (max x, min y),
# (min x, max y) of its box, at mid height.
CORNERS = ((0.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 1.0, 0.5))


def project_tile(loc, rot, bounds_min, bounds_max, surface, z_offset=0.0):
    """`Custom_Projector_with_rotation_fix` with its defaults (`ProjectPosition`, `ProjectRotation`,
    `RestoreOrigZPos` on, `Z_offset_for_proj` 0) on ONE point: `(loc, rot)` after, or None when the
    centre misses the surface (the engine keeps such a point at density 0; it does not occur on a
    terrain that covers the city).

      CopyAttributes_2       `StoredPostion` = the point's position
      ResetPointCenter_0/1/2 the point moved to three corners of its box (`PCGPointHelpers::
                             ResetPointCenter`: loc + RotateVector(q, lerp(min, max, ratio)))
      Projection_1/2/3       each corner dropped onto the surface (positions only)
      AttributeMathsOp_0/1, AttributeVectorOp_0/1, AttributeMathsOp_4/5
                             X = unit(P(1,0) - P(0,0)), Y = unit(P(0,1) - P(0,0))
      MakeRotatorAttribute_0 `MakeRotFromXY(X, Y)` -> `$Rotation` (CopyAttributes_0)
      Projection_0           the point itself dropped onto the surface
      AttributeMathsOp_2/3   `$Position.Z += StoredPostion.Z - Z_offset_for_proj`

    `surface.height(x, y)` is the surface's own sample (`UPCGMeshPartitionData::ProjectPoint` falls back
    to `SamplePoint`, a vertical ray -- the same call `pypcg.ue.terrain.Terrain.height` makes)."""
    h = surface.height(loc[0], loc[1])
    if h is None:
        return None
    q = quat_of(*rot)
    corners = []
    for ratio in CORNERS:
        c = tuple(bounds_min[a] + (bounds_max[a] - bounds_min[a]) * ratio[a] for a in range(3))
        d = quat_rotate(q, c)
        x, y = loc[0] + d[0], loc[1] + d[1]
        hz = surface.height(x, y)
        corners.append((x, y, loc[2] + d[2] if hz is None else hz))
    p0, p1, p2 = corners
    x_axis = _safe_normal((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
    y_axis = _safe_normal((p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]))
    new_rot = rot_from_xy(x_axis, y_axis)
    return (loc[0], loc[1], h + (loc[2] - float(z_offset))), new_rot


# ---- Extract_Segments on an OPEN path --------------------------------------------------------------
def extract_open_segments(path, angle_deg):
    """`Extract_Segments` on an open spline: the runs between the interior control points whose turn
    exceeds `angle_deg`, the two ends always closing a run (`SplitSplines` slices the control points;
    an open spline has no wrap). The closed form is `geo.extract_segments`."""
    pts = [tuple(p) for p in path]
    n = len(pts)
    if n < 2:
        return []
    cuts = [0]
    for i in range(1, n - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu <= 1e-12 or lv <= 1e-12:
            continue
        cosang = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))
        if math.degrees(math.acos(cosang)) > float(angle_deg):
            cuts.append(i)
    cuts.append(n - 1)
    return [pts[cuts[k]:cuts[k + 1] + 1] for k in range(len(cuts) - 1)]
