"""Open-path primitives of the PCGPrimitives Transform / Place / Extract families, as plain polylines
(stage 14 first). A path is `[(x, y, z)]`; every function here reads its geometry as straight segments
between the points, which is what the engine's splines are wherever stage 14 uses them (linear splines,
or curves whose tangents are the chord -- measured on the stage-14 taps, `docs/pypcg/stages/s14.md`).

Each function names the primitive it stands for and the engine node inside it:

  control_yaws      `GetSplineControlPoints` on a linear spline: each point's own rotation is the
                    direction of its outgoing segment, the last point's that of its incoming one
                    (`SplitSpline`'s `GetQuaternionAtSplineInputKey` at a cut end, `PCGSplitSplines.cpp`)
  truncate          `Transform_Truncate` (`SplitSpline(ByDistance)` at StartOffset, keep the remainder,
                    `ReverseSpline`, the same at EndOffset): the result runs REVERSED
  chord             `Transform_Resample` with `SamplingMode = NumberOfSamples` as stage 14 wires it: the
                    path's two ends (measured: every one of the 21 outer runs, 2 to 12 points in, 2 out)
  subdivide         `Transform_Resample`, `Subdivision` mode: every segment cut into `n + 1` equal parts
  resample_fit      `Transform_Resample`, `Distance` mode with `FitToCurve` (`FDistanceStepSampler`,
                    `PCGSplineSampler.cpp`): `N = int(L / d)` samples, `L / (N - 1)` apart; a path shorter
                    than `d` gives NO sample and so no spline
  offset_local      `Transform_Offset` (PerPoints, non-absolute) on a spline: each control point moved by
                    the offset turned by its own rotation (`TransformPoints_1` -> `OffsetSpline_0`)
  pairs             `Extract_Segments` with `CutAngleThreshold` 0 (its default): the predicate is
                    `$Index + 1`, so the spline splits at EVERY control point -- one 2-point run per segment
  center            `Place_Point_AtCenter` on one 2-point run (`ForcePolygonKeepPoints` makes it a polygon):
                    the frame of its first longest segment, the bounding box centre in that frame
"""
import math

from .plane import path_length


def _xyz(p):
    return (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)


def yaw_of(a, b):
    """The yaw in degrees of the direction a -> b (`FRotationMatrix::MakeFromX(...).Rotator().Yaw`)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def control_yaws(path):
    """`GetSplineControlPoints`' yaw for each control point of a linear open path."""
    n = len(path)
    if n < 2:
        return [0.0] * n
    out = [yaw_of(path[i], path[i + 1]) for i in range(n - 1)]
    out.append(yaw_of(path[n - 2], path[n - 1]))
    return out


def _cut_from_start(path, d):
    """The part of `path` after arclength `d` (SplitSpline keeps the LAST piece). No split when `d` is not
    inside the path (`SplitKeys <= FirstKey || >= LastKey` are dropped, the spline passes whole)."""
    pts = [_xyz(p) for p in path]
    if d <= 0.0 or len(pts) < 2:
        return pts
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = math.dist(a[:2], b[:2])
        if acc + seg > d:
            t = (d - acc) / seg
            cut = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))
            return [cut] + pts[i + 1:]
        acc += seg
    return pts


def truncate(path, start, end):
    """`Transform_Truncate`: `start` cm off the start, `end` cm off the end; the result runs from the old
    end towards the old start (the CoreProcess reverses before the second split and never reverses back --
    every one of the stage-14 taps runs that way). A path not longer than an offset keeps that side."""
    pts = _cut_from_start(path, float(start)) if start else [_xyz(p) for p in path]
    pts = list(reversed(pts))
    return _cut_from_start(pts, float(end)) if end else pts


def chord(path):
    """`Transform_Resample (NumberOfSamples)` as stage 14 wires it: the two ends of the path."""
    if len(path) < 2:
        return [_xyz(p) for p in path]
    return [_xyz(path[0]), _xyz(path[-1])]


def subdivide(path, n):
    """`Transform_Resample (Subdivision, n)`: `n` evenly spaced points added inside every segment."""
    pts = [_xyz(p) for p in path]
    if len(pts) < 2:
        return pts
    out = []
    k = int(n) + 1
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        for j in range(k):
            t = j / k
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])))
    out.append(pts[-1])
    return out


def _at(pts, cum, s):
    i = 0
    while i < len(pts) - 2 and cum[i + 1] < s:
        i += 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0.0 else (s - cum[i]) / seg
    a, b = pts[i], pts[i + 1]
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))


def resample_fit(path, distance):
    """`Transform_Resample (Distance, FitToCurve)`: `N = int(L / distance)` points from the start to the
    end, `L / (N - 1)` apart; `[]` -- no spline at all -- when N < 2: a path shorter than `distance` gets no
    sample, and a one-sample spline does not survive `CreateSpline` (measured: 38 cut outer lines in, 31 out,
    the 7 lost ones all under 700 cm)."""
    pts = [_xyz(p) for p in path]
    if len(pts) < 2 or distance <= 0.0:
        return []
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + math.dist(pts[i][:2], pts[i + 1][:2]))
    total = cum[-1]
    n = int(total / float(distance))
    if n < 2:
        return []
    step = total / (n - 1)
    out = [_at(pts, cum, k * step) for k in range(n - 1)]
    out.append(pts[-1])
    return out


def offset_local(path, dx, dy, yaws=None):
    """`Transform_Offset` (PerPoints, non-absolute) on a path: each control point moved by `(dx, dy)`
    turned by its own yaw (`control_yaws` unless given)."""
    pts = [_xyz(p) for p in path]
    yaws = control_yaws(pts) if yaws is None else yaws
    out = []
    for p, yaw in zip(pts, yaws):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        out.append((p[0] + c * dx - s * dy, p[1] + s * dx + c * dy, p[2]))
    return out


def pairs(path):
    """`Extract_Segments (CutAngleThreshold 0)` on an open path: its segments as 2-point runs, in order."""
    pts = [_xyz(p) for p in path]
    return [[pts[i], pts[i + 1]] for i in range(len(pts) - 1)]


def center(run):
    """`Place_Point_AtCenter` on a 2-point run: `(location, yaw)` -- the midpoint (the bounding box centre
    in the run's own frame; z the mean) and the yaw of the run's direction."""
    a, b = _xyz(run[0]), _xyz(run[-1])
    return ((0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (a[2] + b[2])), yaw_of(a, b))


def length(path):
    return path_length([tuple(p[:2]) for p in path])
