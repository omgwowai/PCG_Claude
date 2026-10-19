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

from .plane import extract_segments, path_length, signed_area


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

