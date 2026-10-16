"""The road-specific geometry stage 7 needs from its primitives (spec 2.3). No unreal import.

Every function here stands in for a PCGPrimitives computation subgraph the stage-7 graph calls; the
docstring on each names the subgraph and the nodes inside it. Pure geometry only: the booleans that
need Clipper2 arrive through the `ops` argument, exactly as `pypcg.geo.subdivide` takes them.
"""
import math

from .plane import bbox, drop_closing, enclosing_polygon, inside, path_length, unit
from .types import Polygon, Spline

# `Transform_Outline`'s CoreProcess: `CreatePolygon2D(OpenPolygonWidth = width, EndType = Butt,
# InputType = ForceOpen)` then `OffsetPolygon2D(+-width/2)` and `Polygon2DOperation(Difference)`.
# A Butt end means the ribbon is cut square at the path's ends, which is what an offset band of a
# closed path gives; `enclosing_polygon` closes the path's own ends square onto its box.
OUTLINE_JOIN = "square"
OUTLINE_MITER = 2.0

# `Filter_Splines_byLength` overrides `Length = 1000, Operator = Greater`, so a road section shorter
# than 10 m is dropped (`roadSectionLimit` is the same 200 default the doc names, unused here).
SECTION_LIMIT_CM = 1000.0


def path_of(spline):
    """A spline's dense polyline in XY, or its control points when it carries none."""
    pts = spline.polyline or spline.points
    return drop_closing([(p[0], p[1]) for p in pts])


def extend(path, distance):
    """`Transform_Splines_Extend`: push both ends of an open path out along its end tangents by
    `distance`. The primitive loops a spline-extend over the input; for a linear path the end
    tangent is the adjacent segment's direction, so the first point moves BACK along the first
    segment and the last point FORWARD along the last."""
    if len(path) < 2 or distance == 0.0:
        return list(path)
    a, b = path[-2], path[-1]
    d = unit(b[0] - a[0], b[1] - a[1])                 # the last segment, pointing out
    c, e = path[1], path[0]
    f = unit(e[0] - c[0], e[1] - c[1])                 # the first segment, pointing back
    return [(path[0][0] + f[0] * distance, path[0][1] + f[1] * distance)] + list(path[1:-1]) + \
           [(b[0] + d[0] * distance, b[1] + d[1] * distance)]


def outline(path, width, ops):
    """`Transform_Outline`: the ribbon of `width` around an open path, as `[Polygon]`.

    The CoreProcess (`Transform_Outline_CoreProcess`, 13 nodes) is:

      FilterDataByAttribute_0  keep `$IsClosed == false` -- the OPEN paths only
      CreatePolygon2D_2        `ForceClosed`  <- that same filtered output
      OffsetPolygon2D_0 / _1   `+-width/2`    <- CreatePolygon2D_2
      Polygon2DOperation_0     `Difference`   <- grown minus shrunk
      CreatePolygon2D_0        `ForceOpen`, `OpenPolygonWidth = width`, `EndType = Butt`
      output node               wires BOTH `CreatePolygon2D_0` and `Polygon2DOperation_0`

    The graph's input here is always the road lines, which are open (`FilterDataByAttribute_0`
    selects exactly those), so the left branch is starved: `CreatePolygon2D_2`'s `ForceClosed` ring
    of an open path is a degenerate zero-area polygon, both offsets of it are empty and
    `Polygon2DOperation_0` outputs nothing. **The surviving output is `CreatePolygon2D_0`'s band**,
    which is `UE::Geometry::PolygonsOffset` on the open poly-path in `Butt` mode -- measured
    2026-10-16: a 36 118.85 cm straight path at width 1900 gives exactly `36118.85 x 1900` cm
    (6862.58 m2), i.e. the band spans `+-width/2` and is capped square at both ends. So the ribbon is
    `width` wide, once, and `pypcg.ue.ops.path_offset` produces it directly."""
    if len(path) < 2 or width <= 0.0:
        return []
    return ops.path_offset(path, float(width), end="butt", join=OUTLINE_JOIN, miter_limit=OUTLINE_MITER)


def bands_of(paths, width, ops):
    """`Transform_Outline` over a whole class: one band per path, all of them returned."""
    out = []
    for path in paths:
        out += outline(path, width, ops)
    return out


def union(parts, ops):
    """`Compose_Areas_Union`: the union of every ring given, as polygons. The primitive's CoreProcess
    filters to Polygon2D and runs `Polygon2DOperation(Union)`."""
    rings = []
    for p in parts:
        rings.append(p.outer)
        rings += list(p.holes)
    if not rings:
        return []
    return ops.union(rings) if len(rings) > 1 else [Polygon(list(rings[0]))]


def difference(parts, cutters, ops):
    """`Compose_Areas_Exclusion`: `Polygon2DOperation(Difference)` of the first list minus the rest."""
    a = [r for p in parts for r in [p.outer] + list(p.holes)]
    b = [r for p in cutters for r in [p.outer] + list(p.holes)]
    if not a:
        return []
    if not b:
        return list(parts)
    return ops.difference(a, b)


def expand(parts, distance, ops):
    """`Transform_Areas_Expand`: `OffsetPolygon2D(+Expand, UnionBeforeOutputting = false)` -- one
    polygon in, one polygon out, holes and all. The CoreProcess offsets the Polygon2D list and,
    because `Union` is off, hands the result straight out; a ring that offsets away entirely leaves
    nothing."""
    out = []
    for p in parts:
        res = ops.offset([p.outer], float(distance), OUTLINE_JOIN, OUTLINE_MITER)
        for q in res:
            q.holes = q.holes + [list(h) for h in p.holes]
            out.append(q)
    return out


def clip_at(path, cutters, ops):
    """`Compose_Spline_Cut` (DifferenceOrIntersection false = keep the part OUTSIDE the cutters): an
    open path minus the areas. `ClipPaths` on a 2D boolean; the path is split where it crosses a
    cutter's boundary and the pieces whose midpoint lies inside a cutter are dropped."""
    if not cutters:
        return [list(path)]
    kept, current = [], [path[0]]
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        seg = _clip_segment(a, b, cutters)
        if seg is None:                       # the whole segment runs inside a cutter
            if len(current) > 1:
                kept.append(current)
            current = []
            continue
        for piece, outside in seg:
            if not outside:
                if len(current) > 1:
                    kept.append(current)
                current = []
                continue
            if not current:
                current = []
            if current and _same(current[-1], piece[0]):
                current.append(piece[1])
            else:
                if len(current) > 1:
                    kept.append(current)
                current = [piece[0], piece[1]]
    if len(current) > 1:
        kept.append(current)
    return kept


def _same(a, b, tol=1e-6):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _clip_segment(a, b, cutters):
    """The segment split at every cutter boundary crossing: `[(piece, outside)]`, or None when every
    sample of it lies inside a cutter."""
    ts = {0.0, 1.0}
    for ring in _rings(cutters):
        n = len(ring)
        for i in range(n):
            p, q = ring[i], ring[(i + 1) % n]
            t = _cross(a, b, p, q)
            if t is not None:
                ts.add(t)
    marks = sorted(ts)
    out = []
    for t0, t1 in zip(marks, marks[1:]):
        if t1 - t0 <= 1e-12:
            continue
        tm = 0.5 * (t0 + t1)
        pt = (a[0] + tm * (b[0] - a[0]), a[1] + tm * (b[1] - a[1]))
        outside = not any(inside(pt, ring) for ring in _rings(cutters))
        pa = (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1]))
        pb = (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1]))
        out.append(((pa, pb), outside))
    return out or None


def _rings(cutters):
    for c in cutters:
        yield [(p[0], p[1]) for p in c.outer]
        for h in c.holes:
            yield [(p[0], p[1]) for p in h]


def _cross(a, b, p, q):
    """The parameter t in [0, 1] at which segment a->b crosses segment p->q, or None."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = q[0] - p[0], q[1] - p[1]
    den = rx * sy - ry * sx
    if den == 0:
        return None
    wx, wy = p[0] - a[0], p[1] - a[1]
    t = (wx * sy - wy * sx) / den
    u = (wx * ry - wy * rx) / den
    return t if 0.0 < t < 1.0 and 0.0 <= u < 1.0 else None


def section_length(path):
    return path_length([(p[0], p[1], 0.0) for p in path])


def long_enough(path, limit=SECTION_LIMIT_CM):
    """`Filter_Splines_byLength(Length, Greater)`: `@data.$Length > limit`."""
    return section_length(path) > limit


def spread(parts, spacing, ops):
    """`Place_OnSpline(Spacing)`: points every `spacing` cm along each spline, `FollowCurve` on.

    Returns `[(x, y, yaw_deg, spline_index, distance_along)]`, the point's yaw being the direction of
    travel at it (`Facing = inward` with `MeshForwardAxis = X`)."""
    out = []
    for i, path in enumerate(parts):
        if len(path) < 2:
            continue
        cum = [0.0]
        for j in range(len(path) - 1):
            cum.append(cum[-1] + math.dist(path[j], path[j + 1]))
        total = cum[-1]
        if total <= 0:
            continue
        n = int(total / spacing) + 1
        for k in range(n):
            s = k * spacing
            if s >= total:
                break
            out.append(_at_yaw(path, cum, s, spacing, i, total))
    return out


def _at_yaw(path, cum, s, spacing, index, total):
    import bisect
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    x = path[i][0] + t * (path[i + 1][0] - path[i][0])
    y = path[i][1] + t * (path[i + 1][1] - path[i][1])
    if spacing <= 0:
        yaw = 0.0
    else:
        # FitToCurve on a linear polyline: the direction is taken between the points one spacing
        # either side of this one, clamped at the ends -- what the primitive's own sampler does.
        a = _at_dist(path, cum, max(0.0, s - spacing))
        b = _at_dist(path, cum, min(total, s + spacing))
        yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return (x, y, yaw, index, s)


def _at_dist(path, cum, s):
    import bisect
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    return (path[i][0] + t * (path[i + 1][0] - path[i][0]),
            path[i][1] + t * (path[i + 1][1] - path[i][1]))
