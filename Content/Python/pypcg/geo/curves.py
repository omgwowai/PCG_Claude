"""Curved (Hermite) splines as the engine's `FInterpCurve` / `FSplineCurves` evaluate them, for the stage-16
nodes that edit user-drawn splines rather than linear rings. No unreal import.

A spline here is `(points, tangents, closed)` in WORLD coordinates: `points` the control points, `tangents`
`[(arrive, leave)]` per point (what `pypcg.ue.convert` reads off a `PCGSplineData`: world positions, and the
tangents through the data's `TransformVector`). Every key is the control point's index (the engine's
`InputKey`), so a segment's parameter runs 0..1 and its `Diff` is 1.

  auto_tangents    `FInterpCurve::AutoSetTangents` for `CurveAuto` points (tension 0): `((p - prev) +
                   (next - p)) / 2`. Measured bit for bit on the 38 control points of the two projected
                   lakes (stage 16, t18) and of the two lake beds (t20), whose frames are the identity
  position_at /    `FInterpCurve::Eval` / `EvalDerivative` on a Hermite segment (`FMath::CubicInterp` /
  derivative_at    `CubicInterpDerivative`), in doubles; a linear segment is a lerp
  nearest_key      `FSplineCurves::FindInputKeyClosestToWorldLocation`: the key of the curve point nearest a
                   world location. The engine's search returns a FLOAT key (`FInterpCurve::FindNearest`);
                   this one refines in doubles, so a split point can differ from the engine's by the float
                   key's resolution (about 4e-6 of a segment)
  split            `PCGSplitSpline::SplitSpline` (`PCGSplitSplines.cpp`) on an OPEN spline: the split points
                   at the two keys (position and tangent at the key, the tangent scaled by the key's ratio
                   into its segment -- arrive by `r`, leave by `1 - r`), the control points between kept, the
                   first kept point's arrive tangent scaled by `1 - r_start` and the last's leave by `r_end`
  offset_points    `Transform_Offset` on a spline with `PerPoints` (its CoreProcess: `GetSplineControlPoints`
                   -> `TransformPoints` (the offset in each control point's own frame) -> the moved-minus-old
                   `Direction` -> `OffsetSpline`): each control point moves by `(p + RotateVector(q, offset)) -
                   p`, `q` = `MakeFromXZ(leave tangent, up)`, and each segment's tangents are scaled by its new
                   chord over its old (`PCGOffsetSpline.cpp`)
  reverse          `Transform_Splines_Reverse` (`PCGReverseSpline`): the points in reverse order, every
                   tangent negated (arrive and leave swap roles)
"""
import math

from .frames import make_from_xz
from .plane import quat_rotate

UP = (0.0, 0.0, 1.0)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def auto_tangents(points, closed):
    """`CurveAuto` tangents, tension 0, unit key spacing: `((p - prev) + (next - p)) / 2`. An open curve's
    end point uses itself as its missing neighbour (`AutoSetTangents` with `bStationaryEndpoints` false:
    `ComputeCurveTangent` on (p, p, next) / (prev, p, p))."""
    n = len(points)
    out = []
    for i in range(n):
        p = tuple(points[i])
        if closed:
            prev, nxt = tuple(points[i - 1]), tuple(points[(i + 1) % n])
        else:
            prev = tuple(points[i - 1]) if i > 0 else p
            nxt = tuple(points[i + 1]) if i < n - 1 else p
        t = tuple(((p[k] - prev[k]) + (nxt[k] - p[k])) / 2.0 for k in range(3))
        out.append(t)
    return out


def segments(points, closed):
    n = len(points)
    return n if closed else max(0, n - 1)


def _seg(points, tangents, closed, key):
    """(i, j, alpha) for a key: the segment's start index, end index and the parameter in it."""
    n = len(points)
    nseg = segments(points, closed)
    if nseg <= 0:
        return 0, 0, 0.0
    i = int(math.floor(key))
    if i >= nseg:
        i = nseg - 1
    if i < 0:
        i = 0
    a = key - i
    j = (i + 1) % n
    return i, j, a


def position_at(points, tangents, closed, key, linear=False):
    i, j, a = _seg(points, tangents, closed, key)
    p0, p1 = tuple(points[i]), tuple(points[j])
    if linear or tangents is None:
        return _add(p0, _mul(_sub(p1, p0), a))
    t0, t1 = tuple(tangents[i][1]), tuple(tangents[j][0])
    a2, a3 = a * a, a * a * a
    c0 = 2.0 * a3 - 3.0 * a2 + 1.0
    c1 = a3 - 2.0 * a2 + a
    c2 = a3 - a2
    c3 = -2.0 * a3 + 3.0 * a2
    return tuple(p0[k] * c0 + t0[k] * c1 + t1[k] * c2 + p1[k] * c3 for k in range(3))


def derivative_at(points, tangents, closed, key, linear=False):
    i, j, a = _seg(points, tangents, closed, key)
    p0, p1 = tuple(points[i]), tuple(points[j])
    if linear or tangents is None:
        return _sub(p1, p0)
    t0, t1 = tuple(tangents[i][1]), tuple(tangents[j][0])
    out = []
    for k in range(3):
        aa = 6.0 * p0[k] + 3.0 * t0[k] + 3.0 * t1[k] - 6.0 * p1[k]
        bb = -6.0 * p0[k] - 4.0 * t0[k] - 2.0 * t1[k] + 6.0 * p1[k]
        out.append(aa * a * a + bb * a + t0[k])
    return tuple(out)


def nearest_key(points, tangents, closed, target, samples=64, iters=40):
    """The key of the curve point nearest `target` (3D): per segment a dense sample, then a golden-section
    refinement around the best sample; the best over all segments."""
    nseg = segments(points, closed)
    best = (float("inf"), 0.0)
    for s in range(nseg):
        def f(k, s=s):
            # the segment's own end is evaluated in it (a key of s + 1 would fall into the next segment)
            return _len(_sub(position_at(points, tangents, closed, min(k, s + 1.0 - 1e-15)), target))

        cand = [(f(s + m / float(samples)), m) for m in range(samples + 1)]
        _d0, m0 = min(cand)
        lo = s + max(0, m0 - 1) / float(samples)
        hi = s + min(samples, m0 + 1) / float(samples)
        g = (math.sqrt(5.0) - 1.0) / 2.0
        c, d = hi - g * (hi - lo), lo + g * (hi - lo)

        fc, fd = f(c), f(d)
        for _ in range(iters):
            if fc < fd:
                hi, d, fd = d, c, fc
                c = hi - g * (hi - lo)
                fc = f(c)
            else:
                lo, c, fc = c, d, fd
                d = lo + g * (hi - lo)
                fd = f(d)
        k = (lo + hi) / 2.0
        dk = f(k)
        if dk < best[0]:
            best = (dk, k)
    return best[1]


KEY_EPS = 1.0e-6


def split(points, tangents, start_key, end_key):
    """`SplitSpline` of an OPEN curved spline between two keys: `(points, tangents)` of the piece, every
    tangent explicit (`CurveCustomTangent`; the engine keeps the untouched interior points `CurveAuto`, whose
    recomputed tangents are the originals, since their neighbours are original points)."""
    n = len(points)
    length = float(n - 1)
    start_key = max(start_key, 0.0)
    end_key = min(end_key, length)
    if start_key >= end_key or n < 2:
        return [], []
    info = [(float(i), float(i + 1) if i < n - 1 else length, i) for i in range(n)]
    out_p, out_t = [], []
    cur, idx = start_key, 0
    start_ratio = end_ratio = -1.0
    while cur <= end_key and idx < len(info):
        k0, k1, si = info[idx]
        idx += 1
        end_ratio = -1.0
        if idx < len(info) - 1 and cur >= k1 - KEY_EPS:
            continue
        if abs(cur - k0) <= KEY_EPS:
            out_p.append(tuple(points[si]))
            out_t.append((tuple(tangents[si][0]), tuple(tangents[si][1])))
        else:
            ratio = (cur - k0) / (k1 - k0) if k1 - k0 > 0 else 0.0
            if not out_p:
                start_ratio = ratio
            pos = position_at(points, tangents, False, cur)
            tan = derivative_at(points, tangents, False, cur)
            out_p.append(pos)
            out_t.append((_mul(tan, ratio), _mul(tan, 1.0 - ratio)))
            end_ratio = ratio
        if cur < end_key:
            if k1 <= end_key:
                cur = k1
            else:
                cur = end_key
                idx -= 1
        else:
            break
    if len(out_p) >= 2:
        if start_ratio >= 0.0:
            a, l = out_t[1]
            out_t[1] = (_mul(a, 1.0 - start_ratio), l)
        if end_ratio >= 0.0:
            a, l = out_t[-2]
            out_t[-2] = (a, _mul(l, end_ratio))
    return out_p, out_t


def point_frame(tangent, up=UP):
    """The control point's rotation `GetSplineControlPoints` writes: `MakeFromXZ(direction, up)` (the
    point's own rotation curve is yaw-only on the drawn splines, so its up is the world's)."""
    return make_from_xz(tangent, up)


def offset_points(points, tangents, closed, offset):
    """`Transform_Offset` (`PerPoints`, non-absolute) on a spline: `(points, tangents)` after. Measured on the
    two lake beds (t20, -50 cm): 37 of 38 control points bit for bit, the last 1.5e-11 cm."""
    n = len(points)
    moved = []
    for i in range(n):
        p = tuple(points[i])
        q = point_frame(tuple(tangents[i][1]))
        d = quat_rotate(q, tuple(offset))
        m = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
        direction = (m[0] - p[0], m[1] - p[1], m[2] - p[2])
        moved.append((p[0] + direction[0], p[1] + direction[1], p[2] + direction[2]))
    new_t = [(tuple(a), tuple(l)) for a, l in tangents]
    for s in range(segments(points, closed)):
        j = (s + 1) % n
        old = _len(_sub(tuple(points[s]), tuple(points[j])))
        new = _len(_sub(moved[s], moved[j]))
        ratio = new / old if old > 2.220446049250313e-16 else 1.0
        a, l = new_t[s]
        new_t[s] = (a, _mul(l, ratio))
        a, l = new_t[j]
        new_t[j] = (_mul(a, ratio), l)
    return moved, new_t


def reverse(points, tangents):
    """`Transform_Splines_Reverse`: the points reversed, each tangent negated (a point's new arrive is its
    old leave negated). Measured on the two lake edges (t17): positions and tangents bit for bit."""
    p = [tuple(q) for q in reversed(points)]
    t = [(_mul(tuple(l), -1.0), _mul(tuple(a), -1.0)) for a, l in reversed(tangents)]
    return p, t
