"""Area primitives with the engine's per-input semantics, shared by the lot stages (stage 9 first).

Each function names the PCGPrimitives subgraph it stands for and the engine node inside it:

  exclusion      `Compose_Areas_Exclusion`    -> `Polygon2DOperation(Difference)`
  intersection   `Compose_Areas_Intersection` -> `Polygon2DOperation(Intersection)`
  contract       `Transform_Areas_Contract`   -> `OffsetPolygon2D(-Contract)` [+ `Polygon2DOperation(Union)`]
  by_size        `Filter_Areas_BySize`        -> `FilterDataByAttribute(@data.$area <op> Size * 1e4)`
  min_side / by_edge_length
                 `FilterPolygonByEdgeLength`  -> CleanSpline(10 cm) + `Extract_Segments(20 deg)` + min length

`Polygon2DOperation` runs ONE input polygon at a time against the union of every clip polygon
(`PCGPolygon2DOperation.cpp`, `ExecutionLoopMode = SinglePrimaryPin`; the per-polygon loop at the
end of `ExecuteInternal`), and every polygon of the result becomes its own data item. An EMPTY clip
pin passes the inputs through unchanged (the `ClipPolygons.IsEmpty()` branch) -- for an
intersection as much as for a difference. These functions keep all three rules: a list in, one
result list per input, concatenated in input order, and no clip means no change.

Holes travel as extra rings: the engine's booleans use Clipper2's `NonZero` fill
(`PolygonIntersectionUtils.cpp`), outer rings are counter-clockwise and holes clockwise (which is
how `pypcg.ue.convert` reads them), so a hole passed as its own ring cancels its outer. No slivers
are dropped: the official stage-9 outputs keep pieces down to 0.0 m2."""
import math

from .plane import ccw, drop_closing, extract_segments, path_length, signed_area, xy
from .types import Polygon, Spline


def area_of(v):
    """A closed area as a `Polygon`: a Polygon as it is, a CLOSED spline's polyline (`CreatePolygon2D
    ForceClosed`, 1 cm discretisation, which is what `convert` reads the polyline with). An open spline
    is no area: `Compose_Shared_InputsProcessing` forwards it and the CoreProcess filters it out.
    (Moved here from stage 9, its first user, when stage 10 needed the same read.)"""
    if isinstance(v, Polygon):
        return v
    if isinstance(v, Spline) and v.closed:
        r = drop_closing(xy(v.polyline or v.points))
        return Polygon(ccw(r)) if len(r) >= 3 else None
    return None


def areas_of(items, tag=None):
    """The areas of a pin's `(value, tags)` items, optionally only those carrying `tag` (the
    `Filter_Tags` primitive, which compares tags exactly)."""
    out = []
    for v, tags in items:
        if tag is not None and tag not in tags:
            continue
        p = area_of(v)
        if p is not None:
            out.append(p)
    return out


def rings(polys):
    """Every ring of every polygon: the outer, then its holes."""
    return [r for p in polys for r in [p.outer] + list(p.holes)]


def area_cm2(p):
    """`@data.$area`: the outer's area less its holes', in cm2."""
    return abs(signed_area(p.outer)) - sum(abs(signed_area(h)) for h in p.holes)


def exclusion(subjects, clips, ops):
    """`Compose_Areas_Exclusion`: each subject minus the union of all clips."""
    if not clips:
        return list(subjects)
    cut = rings(clips)
    out = []
    for p in subjects:
        out += ops.difference([p.outer] + list(p.holes), cut)
    return out


def intersection(subjects, clips, ops):
    """`Compose_Areas_Intersection`: each subject intersected with the union of all clips. No clip
    passes the subjects through, as the engine node does."""
    if not clips:
        return list(subjects)
    cut = rings(clips)
    out = []
    for p in subjects:
        out += ops.intersection([p.outer] + list(p.holes), cut)
    return out


def expand(polys, distance, ops, union=False):
    """`Transform_Areas_Expand`: `OffsetPolygon2D(+Expand)` on each polygon, holes included (they shrink),
    then -- only when `UnionBeforeOutputting`, which defaults to FALSE on this primitive (its user
    parameter, read 2026-10-19) -- `Polygon2DOperation(Union)` over everything. One polygon in, one
    out, so overlapping neighbours stay two items."""
    out = []
    for p in polys:
        out += ops.offset([p.outer] + list(p.holes), float(distance))
    if union and len(out) > 1:
        return ops.union(rings(out))
    return out


# The frame a `CreatePolygon2D` gives a polygon: a yaw of -90 degrees (probed 2026-10-19 on every Lots,
# district and road-footprint polygon of the demo level) about its own vertices' mean. The engine's
# booleans run in that frame, and Clipper's choice of each result ring's FIRST vertex follows it.
FRAME_QUAT = (0.0, 0.0, -0.7071067811865475, 0.7071067811865476)
_FRAME_INV = (0.0, 0.0, 0.7071067811865475, 0.7071067811865476)


def in_frame(poly, fn):
    """Run `fn(polygon) -> [Polygon]` with `poly` expressed in its CreatePolygon2D frame, and bring the
    results back to the world. Only the start vertex of a result ring depends on this (measured on
    stage 10's grown City outline: computed in the world, the ring starts 754 vertices later than the
    official one; in this frame it starts on the official vertex, to 1.1e-10 cm)."""
    from .plane import quat_rotate
    n = len(poly.outer)
    if n == 0:
        return fn(poly)
    cx, cy = sum(p[0] for p in poly.outer) / n, sum(p[1] for p in poly.outer) / n

    def to_l(ring):
        return [tuple(quat_rotate(_FRAME_INV, (p[0] - cx, p[1] - cy, 0.0))[:2]) for p in ring]

    def to_w(ring):
        out = []
        for p in ring:
            v = quat_rotate(FRAME_QUAT, (p[0], p[1], 0.0))
            out.append((v[0] + cx, v[1] + cy))
        return out

    res = fn(Polygon(to_l(poly.outer), [to_l(h) for h in poly.holes], poly.z))
    return [Polygon(to_w(r.outer), [to_w(h) for h in r.holes], poly.z) for r in res]


def contract(polys, distance, ops, union=True):
    """`Transform_Areas_Contract`: `OffsetPolygon2D` by `-distance` (square joins, the node's
    default), then -- `UnionBeforeOutputting`, true by default and left so by stage 9 --
    `Polygon2DOperation(Union)` over everything the offset produced. The union node only runs with
    two or more polygons; one passes through."""
    out = []
    for p in polys:
        out += ops.offset([p.outer] + list(p.holes), -float(distance))
    if union and len(out) > 1:
        return ops.union(rings(out))
    return out


def follow_subjects(results, subjects):
    """The order and the start vertex the engine gives an offset's results (`OffsetPolygon2D`, with or
    without `Transform_Areas_Contract`'s union): each result in the order of the subject it came from (the
    subject whose ring holds its vertex mean, else the nearest by vertex mean), its ring turned to start at
    the vertex nearest that subject's FIRST vertex. Measured on stage 14's taps (2026-10-20): the outer
    contract 5 of 5, the inner contract 4 of 4, the median expansion 5 of 5, the aisle contract 33 of 36 (the
    three others carry duplicated vertices); every union output in subject order. Booleans computed in the
    world (or in a frame other than the polygon's stored one, trap 68) start elsewhere, and a ring's start
    decides its "first longest edge" -- the frame `Subdivide_Areas_withGrid` lays its grid from."""
    import math as _m
    from .plane import inside

    def mean(r):
        n = len(r)
        return (sum(q[0] for q in r) / n, sum(q[1] for q in r) / n) if n else (0.0, 0.0)

    keyed = []
    for k, p in enumerate(results):
        if not p.outer:
            continue
        c = mean(p.outer)
        idx = [i for i, s in enumerate(subjects) if s.outer and inside(c, s.outer)]
        i = idx[0] if idx else min(range(len(subjects)), key=lambda j: _m.dist(mean(subjects[j].outer), c)) \
            if subjects else 0
        ring = list(p.outer)
        if subjects:
            first = subjects[i].outer[0]
            s = min(range(len(ring)), key=lambda j: _m.dist(ring[j][:2], first[:2]))
            ring = ring[s:] + ring[:s]
        keyed.append((i, k, Polygon(ring, [list(h) for h in p.holes], p.z)))
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [p for _i, _k, p in keyed]


def by_size(polys, size_m2, greater=True):
    """`Filter_Areas_BySize`: (selected, unselected). `Operator = Greater` keeps an area strictly
    larger than `Size` m2, `Lesser` one strictly smaller (the CoreProcess compares `@data.$area` in
    cm2 against `Size * 10000`)."""
    limit = float(size_m2) * 1e4
    sel, rest = [], []
    for p in polys:
        a = area_cm2(p)
        (sel if (a > limit if greater else a < limit) else rest).append(p)
    return sel, rest


FUSE_CM = 10.0           # CleanSpline_0 ColocationDistanceThreshold
SIDE_ANGLE_DEG = 20.0    # Subgraph_0 Extract_Segments CutAngleThreshold


def _fused(ring, threshold=FUSE_CM):
    out = []
    for q in ring:
        if not out or math.dist(out[-1][:2], q[:2]) > threshold:
            out.append(tuple(q[:2]))
    while len(out) > 2 and math.dist(out[0], out[-1]) <= threshold:
        out.pop()
    return out


def min_side(p):
    """`FilterPolygonByEdgeLength`'s `MinLenght`: the outer ring as a closed linear spline, control
    points closer than 10 cm fused (`CleanSpline_0`), cut at every corner over 20 degrees
    (`Extract_Segments`), and the shortest of the resulting runs (`AttributeReduce(Min)` of
    `@data.$Length`). The 5-degree collinear pass of `CleanSpline_0` does not move a run's ends and
    only straightens it, so it is left out (it shortens a run by well under a centimetre)."""
    ring = _fused(p.outer)
    if len(ring) < 3:
        return 0.0
    runs = extract_segments(ring + [ring[0]], SIDE_ANGLE_DEG)
    return min(path_length(r) for r in runs) if runs else 0.0


def by_edge_length(polys, threshold_cm, greater=True):
    """`FilterPolygonByEdgeLength`: (InsideFilter, Outside Filter) -- inside when the shortest side
    is strictly greater (`Filter_Operator = Greater`) than `threshold_cm`."""
    inside, outside = [], []
    for p in polys:
        s = min_side(p)
        (inside if (s > threshold_cm if greater else s < threshold_cm) else outside).append(p)
    return inside, outside

