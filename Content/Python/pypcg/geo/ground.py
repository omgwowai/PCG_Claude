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


def project_tile(loc, rot, bounds_min, bounds_max, surface, z_offset=0.0, scale=(1.0, 1.0, 1.0), quat=None):
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

    The corners are placed with `FTransform::TransformVector` -- the point's SCALE, then its rotation
    (`PCGPointHelpers.h:89-97`); stage 10's tiles have scale 1, stage 13's plaza kit points do not (measured
    2026-10-19: without the scale 1 044 of 32 108 plaza points tilted up to 0.25 deg off the official). `quat`
    is the point's engine quaternion when the caller has it (`Points.quat`), else `rot` is converted.

    `surface.height(x, y)` is the surface's own sample (`UPCGMeshPartitionData::ProjectPoint` falls back
    to `SamplePoint`, a vertical ray -- the same call `pypcg.ue.terrain.Terrain.height` makes)."""
    h = surface.height(loc[0], loc[1])
    if h is None:
        return None
    q = tuple(quat) if quat is not None else quat_of(*rot)
    corners = []
    for ratio in CORNERS:
        c = tuple((bounds_min[a] + (bounds_max[a] - bounds_min[a]) * ratio[a]) * scale[a] for a in range(3))
        d = quat_rotate(q, c)
        x, y = loc[0] + d[0], loc[1] + d[1]
        hz = surface.height(x, y)
        corners.append((x, y, loc[2] + d[2] if hz is None else hz))
    p0, p1, p2 = corners
    x_axis = _safe_normal((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
    y_axis = _safe_normal((p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]))
    new_rot = rot_from_xy(x_axis, y_axis)
    return (loc[0], loc[1], h + (loc[2] - float(z_offset))), new_rot


# ---- the tile ways: Filter_RandomChoice chain + one static mesh per way (stages 10, 13) -------------
def split_ways(n, ratios, rng):
    """A chain of `Filter_RandomChoice` nodes (`RandomPerDataset`, the primitive's default), each keeping a
    share `ratios[k]` of what the previous one left over: one draw per remaining ITEM at each step
    (`geo.keep_each`), the last step's Unselected the final way. Returns the way (0 .. len(ratios)) of each
    of the n items. Stage 10's `FC_RandomChoice_1..6` and stage 13's `Subgraph_59..64` (moved here from
    stage 10 when stage 13 needed the same chain)."""
    from .sample import keep_each
    way = [len(ratios)] * n
    left = list(range(n))
    for k, ratio in enumerate(ratios):
        keep = keep_each(len(left), ratio, rng)
        for i, f in zip(left, keep):
            if f:
                way[i] = k
        left = [i for i, f in zip(left, keep) if not f]
    return way


def assign_ways(sets, way, table, calls, offset):
    """One `Assign_Assets` call per way, each with a single static mesh and `PositionOffset` = `offset`:
    the call merges its items' points (`$Seed += dataIndex`, the item's index in that call's input) and,
    the asset being a static mesh, outputs the moved targets alone with the mesh's box
    (`geo.assets.expand_items`). `calls` is `[(letter, path)]` in the ways' order and `table[k]` the loaded
    entry of `calls[k]`. Returns `{letter: Points}` for the calls that got points."""
    from . import assets as AS
    from .types import Points
    out = {}
    for k, (letter, _path) in enumerate(calls):
        mine = [sets[i] for i in range(len(sets)) if way[i] == k]
        targets = Points()
        for idx, s in enumerate(mine):
            for j in range(len(s)):
                targets.add(s.loc[j], rot=s.rot[j], scale=s.scale[j], density=s.density[j],
                            bounds_min=s.bounds_min[j], bounds_max=s.bounds_max[j], color=s.color[j],
                            steepness=s.steepness[j], seed=AS._i32(int(s.seed[j]) + idx))
        if not len(targets):
            continue
        items = AS.expand_items(targets, [table[k]], [0] * len(targets), {"position_offset": offset})
        if items:
            out[letter] = items[-1]
    return out


# ---- Fill_Areas_Randomly ---------------------------------------------------------------------------
def fill_random(poly, per_m2, rng, sampling_extent=1.0):
    """`Fill_Areas_Randomly` (`Uniformity` 0, `FinalCount` -1, zero ranges: the primitive's defaults) on ONE
    polygon, with Python's own numbers (spec E2). The CoreProcess's `SurfaceSampler_1` (`bUnbounded`,
    `Looseness` = 1 - `Uniformity` = 1) lays a grid over the polygon's bounds whose cell is
    `sqrt(1e4 / PointsPerSquaredMeter)` cm (the non-legacy grid, `PCGSurfaceSampler.cpp:66-97`: square
    `SamplingPointExtents` (1, 1, 1)), cells `CeilToInt(min / cell) .. FloorToInt(max / cell)`; each cell
    gets ONE point jittered over the cell less the point's own size (`InnerCellSize` = cell - 2 x extent,
    `InnerCellOffset` 0), kept when the polygon's interior holds it (`ProjectPoint` on the interior
    surface; holes excluded). The engine draws each cell from `FRandomStream(ComputeSeed(Seed, X, Y))`;
    the port draws from `rng`, so the count follows the same grid and the layout is new.
    Returns the world locations (z = the polygon's)."""
    from .plane import inside
    if per_m2 <= 0 or len(poly.outer) < 3:
        return []
    cell = math.sqrt(1e4 / float(per_m2))
    inner = cell - 2.0 * float(sampling_extent)
    xs, ys = [p[0] for p in poly.outer], [p[1] for p in poly.outer]
    i0, i1 = math.ceil(min(xs) / cell), math.floor(max(xs) / cell)
    j0, j1 = math.ceil(min(ys) / cell), math.floor(max(ys) / cell)
    out = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            x = i * cell + rng.random() * inner
            y = j * cell + rng.random() * inner
            if inside((x, y), poly.outer) and not any(inside((x, y), h) for h in poly.holes):
                out.append((x, y, float(poly.z)))
    return out


def project_point(loc, rot, bounds_min, bounds_max, surface, z_offset=0.0, scale=(1.0, 1.0, 1.0), quat=None):
    """`Custom_Projector_with_rotation_fix` on ONE point, MISSES included: `(loc, rot, hit)`. A hit is
    `project_tile`'s result. On a miss the point stays where it is (`Projection_0` keeps it,
    `bKeepZeroDensityPoints`) at density 0, its rotation unchanged, and `AttributeMathsOp_2/3` still add the
    stored z, so its z doubles -- measured 2026-10-19 on stage 13's highway tiles outside the terrain
    (`Subgraph_57`: z 841.95 -> 1683.90, density 0). The caller sets the density to 0 when `hit` is False."""
    res = project_tile(loc, rot, bounds_min, bounds_max, surface, z_offset, scale, quat)
    if res is not None:
        return res[0], res[1], True
    return (loc[0], loc[1], loc[2] + (loc[2] - float(z_offset))), tuple(rot), False


# ---- Compose_Points_Difference (Discrete, Binary) ---------------------------------------------------
def _matrix(loc, q, scale):
    from .assets import _matrix as m
    return m(loc, q, scale)


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _inverse(m):
    """The inverse of an affine row-vector matrix (rows 0..2 the axes, row 3 the origin)."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if det == 0.0:
        return None
    inv = [[(a[(c + 1) % 3][(r + 1) % 3] * a[(c + 2) % 3][(r + 2) % 3]
             - a[(c + 1) % 3][(r + 2) % 3] * a[(c + 2) % 3][(r + 1) % 3]) / det for c in range(3)] for r in range(3)]
    t = m[3][:3]
    ti = [-(t[0] * inv[0][c] + t[1] * inv[1][c] + t[2] * inv[2][c]) for c in range(3)]
    return [inv[0] + [0.0], inv[1] + [0.0], inv[2] + [0.0], ti + [1.0]]


def _box_by(lo, hi, m):
    """`FBox::TransformBy(FMatrix)`: the axis-aligned box of the eight transformed corners."""
    xs, ys, zs = [], [], []
    for x in (lo[0], hi[0]):
        for y in (lo[1], hi[1]):
            for z in (lo[2], hi[2]):
                xs.append(x * m[0][0] + y * m[1][0] + z * m[2][0] + m[3][0])
                ys.append(x * m[0][1] + y * m[1][1] + z * m[2][1] + m[3][1])
                zs.append(x * m[0][2] + y * m[1][2] + z * m[2][2] + m[3][2])
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _overlap_ratio(a, b):
    """`FBox::Overlap` then `ComputeOverlapRatio(Overlap, b)` (PCGBasePointData.cpp:99-107): 0 when the boxes do
    not meet (`FBox::Intersect` is inclusive, so touching boxes DO meet, with a zero-thickness overlap); else the
    product over the axes of the overlap's extent over `b`'s, an axis on which `b` has no extent counting 1."""
    lo = [max(a[0][k], b[0][k]) for k in range(3)]
    hi = [min(a[1][k], b[1][k]) for k in range(3)]
    if any(lo[k] > hi[k] for k in range(3)):
        return 0.0
    ratio = 1.0
    for k in range(3):
        den = (b[1][k] - b[0][k]) * 0.5
        ratio *= ((hi[k] - lo[k]) * 0.5) / den if den > 0.0 else 1.0
    return ratio


def density_scale(steepness):
    """`GetLocalDensityBounds`' factor `2 - Steepness`, in floats (the steepness is a float)."""
    from .frames import f32
    return f32(2.0 - f32(steepness))


def _prepared_diff(diff, steepness):
    """A difference point ready for `_overlap_core`: (its matrix, density box min, max)."""
    k = density_scale(steepness)
    return (_matrix(diff[0], diff[1], diff[2]), tuple(k * v for v in diff[3]), tuple(k * v for v in diff[4]))


def _overlap_core(pm, dmin, dmax, qinv, qmin, qmax):
    """`VolumeOverlap` on prepared operands: the diff point's matrix and density box, the query's INVERSE matrix
    and its plain box."""
    p2q = _mul(pm, qinv)
    first = _overlap_ratio(_box_by(dmin, dmax, p2q), (qmin, qmax))
    if first <= 0.0:
        return 0.0
    q2p = _inverse(p2q)
    if q2p is None:
        return 0.0
    qb = _box_by(qmin, qmax, q2p)
    second = _overlap_ratio((dmin, dmax), qb)          # the denominator is the TRANSFORMED query box
    if second <= 0.0:
        return 0.0
    return min(first, second)


def volume_overlap(diff, query, steepness=1.0):
    """`PCGPointHelpers::VolumeOverlap` (PCGBasePointData.cpp:110-137) of a difference point over a query point,
    both `(loc, quat, scale, bounds_min, bounds_max)`: the diff point's DENSITY box (its bounds times `2 -
    steepness`, `GetLocalDensityBounds`; steepness 1 = the bounds) taken into the query's frame and overlapped
    with the query's box (its plain bounds: `SampleBasedRangeProcessing` samples with `GetLocalBounds`), over the
    query box; and the query box taken into the diff's frame and overlapped with the diff box, over that
    transformed query box; the smaller of the two ratios."""
    qinv = _inverse(_matrix(query[0], query[1], query[2]))
    if qinv is None:
        return 0.0
    pm, dmin, dmax = _prepared_diff(diff, steepness)
    return _overlap_core(pm, dmin, dmax, qinv, tuple(query[3]), tuple(query[4]))


BROAD_PHASE_SLACK_CM = 0.01     # the world boxes of the broad phase are grown by this much: it only admits pairs


def difference_binary(sources, diffs, cell=2000.0, drop_empty_sources=False):
    """`Compose_Points_Difference` (`Difference_0`: `Mode` Discrete, `DensityFunction` Binary): a source point is
    REMOVED when the difference points sampled with its own transform and box give a density above 0, i.e.
    when some difference point of density > 0 overlaps it with positive volume (`volume_overlap`). Both
    arguments are lists of `(loc, quat, scale, bounds_min, bounds_max, density[, steepness])` (steepness 1 when
    absent); returns the kept source indices. A difference point of density 0 (a projector miss) removes nothing.

    The pairs are found as the engine's octree does, conservatively: each diff point's world density box and each
    source's world box (`FBox::TransformBy`, grown by `BROAD_PHASE_SLACK_CM`) on a `cell` grid; only pairs whose
    world boxes meet are tested, and the test itself is the exact `VolumeOverlap`. (Stage 12 fix: the first form,
    a fixed reach around every source, ran 109 s on stage 12's 9 137 x 19 134 points.)

    `drop_empty_sources`: the engine keeps a point only when `source density - sampled density > 0`
    (PCGDifferenceData.cpp:316), so whenever the Differences pin holds any spatial data a source point of density 0
    goes too (the caller knows whether it does). Stage 12 sets it; stage 13 (its first user) predates the reading
    and keeps the old behaviour."""
    import math as _m
    e = BROAD_PHASE_SLACK_CM

    def cells(box):
        return [(gx, gy) for gx in range(int(_m.floor((box[0][0] - e) / cell)), int(_m.floor((box[1][0] + e) / cell)) + 1)
                for gy in range(int(_m.floor((box[0][1] - e) / cell)), int(_m.floor((box[1][1] + e) / cell)) + 1)]

    prepared, grid = [], {}
    for d in diffs:
        if d[5] <= 0.0:
            continue
        pm, dmin, dmax = _prepared_diff(d, d[6] if len(d) > 6 else 1.0)
        world = _box_by(dmin, dmax, pm)
        for key in cells(world):
            grid.setdefault(key, []).append(len(prepared))
        prepared.append((pm, dmin, dmax, world))
    kept = []
    for i, s in enumerate(sources):
        if drop_empty_sources and not s[5] > 0.0:
            continue
        qm = _matrix(s[0], s[1], s[2])
        qinv = _inverse(qm)
        qmin, qmax = tuple(s[3]), tuple(s[4])
        world = _box_by(qmin, qmax, qm)
        hit = False
        seen = set()
        if qinv is not None:
            for key in cells(world):
                for j in grid.get(key, ()):
                    if j in seen:
                        continue
                    seen.add(j)
                    pm, dmin, dmax, w = prepared[j]
                    if any(w[0][k] - e > world[1][k] + e or world[0][k] - e > w[1][k] + e for k in range(3)):
                        continue
                    if _overlap_core(pm, dmin, dmax, qinv, qmin, qmax) > 0.0:
                        hit = True
                        break
                if hit:
                    break
        if not hit:
            kept.append(i)
    return kept


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
