"""The road-specific geometry stage 7 needs from its primitives (spec 2.3). No unreal import.

Every function here stands in for a PCGPrimitives computation subgraph the stage-7 graph calls; the
docstring on each names the subgraph and the nodes inside it. Pure geometry only: the booleans that
need Clipper2 arrive through the `ops` argument, exactly as `pypcg.geo.subdivide` takes them.

This module is stage 7's FOOTPRINT half: `Subgraph_86/87/88 Transform_Outline` (the three classes'
ribbons) and `Subgraph_89 Compose_Areas_Union` (their union, the published `RoadFootprints`). The
SECTIONS half -- `Intersection_solving` and everything the six grammar nodes and the decal chain
read -- is `pypcg.geo.sections`.
"""
from .plane import drop_closing, unit
from .types import Polygon

# `Transform_Outline`'s CoreProcess closes the open path into its `ForceOpen` band with
# `CreatePolygon2D(OpenPolygonWidth = width, EndType = Butt)`, i.e. `UE::Geometry::PolygonsOffset`
# on an open poly-path; the renderer for that is `pypcg.ue.ops.Ops.path_offset`. These are the join
# settings both that call and `OffsetPolygon2D` leave at their defaults.
OUTLINE_JOIN = "square"
OUTLINE_MITER = 2.0



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


def outline_ring(ring, width, ops):
    """`Transform_Outline`'s `ForceClosed` branch: the band between `ring` grown by `width/2` and
    shrunk by it, i.e. `Polygon2DOperation(Difference)` of the two offsets.

    Read out of `Transform_Outline_CoreProcess` (the primitive's own dump):

      CreatePolygon2D_2       `ForceClosed` over the closed input -> the ring
      OffsetPolygon2D_0 / _1  `+-width/2`
      Polygon2DOperation_0    Difference: grown MINUS shrunk

    For an open path that branch is empty (the `ForceClosed` ring of an open path is degenerate), so
    `outline` above serves the open case and this one the closed case. The primitive wires both to
    its output, so a caller picks the branch its input warrants -- stage 7's rings (the City outline
    and the Landmarks ribbon) take this one."""
    grown = ops.offset([list(ring)], 0.5 * float(width), OUTLINE_JOIN, OUTLINE_MITER)
    shrunk = ops.offset([list(ring)], -0.5 * float(width), OUTLINE_JOIN, OUTLINE_MITER)
    if not grown:
        return []
    if not shrunk:
        return grown
    return ops.difference([p.outer for p in grown], [p.outer for p in shrunk])


