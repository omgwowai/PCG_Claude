"""`Intersection_solving` (170 nodes) as plain computation. No unreal import.

Stage 7's sections half. The primitive takes the three road classes and returns, per class, that
class's centerline split into the pieces between intersections and the pieces inside them, plus the
intersection polygons the terrain flattening works on. Everything after it in the stage -- the six
grammar assignments, the crosswalk chain, the decals and the road mesh -- reads one of those four
outputs, which is why this file exists.

Read out of the primitive's own IR (`Saved/t10/is_table.txt`, exported 2026-10-17) and of the
embedded `Loop_0` body (`Saved/graph_dumps/embed/embed_Loop_body.json`). The steps below are the data
flow, and each names the official nodes it stands for.

  1. EXTEND.  `Subgraph_1/2/3 Extend <class> Road Splines` -- `Transform_Splines_Extend` per class,
     `distance = <class width>/2` (`AttributeMathsOp_0/1/2`).
  2. OUTLINE EACH CLASS PLAIN.  `Subgraph_116/115/127 Outline <class> Roads` at the class width.
  3. THE INTERSECTION PLANES.  `FilterDataByType_7/8/9` (keep `Polygon2D`) -> `Loop_0` ->
     `Subgraph_151 Transform_Areas_Expand(Expand = intersection_expansion_range)`, declared
     `intersection_Base_Expanded`. The loop body (`...:PCGGraph_0`, 5 nodes) is
     `FilterDataByIndex(loop index)` + `Polygon2DOperation(Intersection)`: one iteration is "this
     ring's outline intersected with all the others'".
  4. THE CUTTER.  `Subgraph_124 Union Road Outlines (Intersection Cutter)` unions the artery
     outline (`Subgraph_114`) with the collector outline minus artery (`Subgraph_136` minus
     `Subgraph_127` through `Subgraph_152`) and the local outline minus artery and collector
     (`Subgraph_143` through `Subgraph_153`).
  5. THE +/-Y DANCE, one per class, which is what produces those three ribbons.  For each side:
     `Transform_Offset(PerPoints, offset = +-width/2)` (`Subgraph_129/130`), `Compose_Spline_Cut`
     with `DifferenceOrIntersection = true` against the expanded planes (so the piece INSIDE is
     kept, `Subgraph_119/121`), `Transform_Offset` back by the opposite amount
     (`Subgraph_131/132`), `AttributeMathsOp_7/9/11/13` zeroing `$Rotation.Roll` and `.Pitch` so the
     outline is planar, then `Transform_Outline` at the class width. The four `Subgraph_1xx` nodes
     the OUTLINE takes (`AttributeMathsOp_4/6`, `_12/14`, `_8/10`) are those planarised pieces, one
     input per side.
  6. THE SECTIONS.  `Subgraph_154/156/158 Clip <class> Roads At Intersections` (Compose_Spline_Cut,
     Difference) cut the class's own extended lines with the cutter -- the sections BETWEEN
     intersections; `Subgraph_133/135/138` (DifferenceOrIntersection = true) keep the pieces INSIDE.
  7. LENGTH.  `Subgraph_4/5/6 Filter_Splines_byLength(Length = roadSectionLimit, Operator =
     Greater)` splits each of those two into a long part and a short part. `AddTags_*` then label
     them: the long ones `roadSections`, the short ones `intersectionsShort`, and every inside piece
     `intersections` (`AddTags_3/4/5`). `Gather_0/1/2` collects the three label groups per class.
  8. THE PLANAR SET.  `Subgraph_144` unions the outlines of "the pieces that are short or inside"
     (`Subgraph_148/145/149` over the short and the inside data) -- `IntersectionsPlanar`.

The primitive also publishes its own `RoadsFootprints` (`Subgraph_191`, the union of the three plain
outlines). It is NOT the stage's published `RoadFootprints`: that one is the footprint half's union
over the DISTRICTS lines, and this primitive's own is unused at stage level, so it is not
reproduced here.
"""
import bisect
import math

from .plane import clip_path, path_length
from .roads import OUTLINE_JOIN, OUTLINE_MITER, extend, outline, outline_ring
from .types import Polygon

# `Subgraph_4/5/6`'s `Length` override. The official node's comment: "No road module under 200 cm
# exists, meaning road sections shorter than this are discarded."
SECTION_LIMIT = 200.0
# `Subgraph_2`'s demo-level override. The graph's own default for `intersection_expansion_range` is
# 100; the demo level runs it at 50, and the oracle this module is checked against was generated
# with 50.
EXPANSION_RANGE = 50.0

LOCAL, COLLECTOR, ARTERY = "localRoads", "CollectorRoads", "ArteryRoads"
CLASSES = (LOCAL, COLLECTOR, ARTERY)
WIDTH_PARAM = {LOCAL: "local_Width", COLLECTOR: "collector_width", ARTERY: "Artery_width"}


def is_closed(path):
    """Whether a path is a closed ring: its ends coincide."""
    return len(path) > 2 and abs(path[0][0] - path[-1][0]) < 1e-6 and abs(path[0][1] - path[-1][1]) < 1e-6


def offset_path(path, dy):
    """`Transform_Offset` with `PerPoints` on: translate every point by the same XY vector.

    The official nodes build that vector with `MakeVectorAttribute` from the class's half width
    (`MakeVec_Local_Pos` = (0, +half, 0), `MakeVec_Local_Neg` = (0, -half, 0)), so the offset is a
    plain translation; the XY of those vectors is always X=0, Z=0, Y=+-half. Independent of Y as a
    world axis: this is a 2D graph and the offset is the sign-carrying lateral shift the graph's
    `AttributeMathsOp_*` half-widths compute."""
    if dy == 0.0:
        return list(path)
    return [(p[0], p[1] + dy) + tuple(p[2:]) for p in path]


def outline_class(paths, width, ops):
    """`Subgraph_116/115/127 Outline <class> Roads`: one ribbon per path at `Width`, open paths on
    `Transform_Outline`'s `ForceOpen` branch and closed ones on its `ForceClosed` branch."""
    out = []
    for path in paths:
        if is_closed(path):
            out += outline_ring(path[:-1], width, ops)
        else:
            out += outline(path, width, ops)
    return out


def intersection_planes(ribbons, expand, ops):
    """STEP 3: the `Loop_0` sweep, then `Subgraph_151`'s expansion. `ribbons` is `[Polygon]`.

    Each ribbon is intersected as the whole polygon, holes included: `Polygon2DOperation` works on the
    Polygon2D data, so a closed ring's band (the City outline, `Transform_Outline`'s `ForceClosed`
    branch) covers its band only, not the disk inside it. The holes go in as their own rings; the
    booleans fill NonZero and the engine returns holes clockwise, so they subtract (probed 2026-10-21,
    `pyg_probe_t27_holes.py`). Reading only the outer ring made the town's City band intersect every
    road inside the city: one 70 ha "intersection" where the official primitive gives 107 planes
    (Task 27, ruling T27g). With no holed ribbon -- the demo's input -- the rings are the same as before."""
    rings = [[list(p.outer)] + [list(h) for h in p.holes] for p in ribbons]
    if len(rings) < 2:
        return []
    pieces = []
    for i, own in enumerate(rings):
        others = [r for j, rs in enumerate(rings) if j != i for r in rs]
        pieces += ops.intersection(own, others)
    if not pieces:
        return []
    if expand <= 0.0:
        return pieces
    out = []
    for p in pieces:
        for q in ops.offset([p.outer], float(expand), OUTLINE_JOIN, OUTLINE_MITER):
            q.holes = q.holes + [list(h) for h in p.holes]
            out.append(q)
    return out


def side_ribbons(paths, width, planes, ops):
    """STEP 5: one class's two ribbons, as `[Polygon]` (both sides, in graph order: -Y then +Y,
    the order `Subgraph_114`'s two `PrimaryInput` edges arrive in)."""
    half = 0.5 * float(width)
    out = []
    for dy in (half, -half):
        shifted = [offset_path(p, dy) for p in paths]
        inside = cut_paths(shifted, planes, ops, True)
        back = [offset_path(p, -dy) for p in inside]
        out += outline_class(back, width, ops)
    return out


def cut_paths(paths, rings, ops, inside):
    """`Compose_Spline_Cut`: the parts of each open path inside the clip rings, or outside them.

    Both directions occur in this stage with the same primitive: `DifferenceOrIntersection` left at
    its default (false) is Difference -- `Subgraph_27/28/13` (the landmark clips) and
    `Subgraph_154/156/158` (the intersection clips) -- and `true` is Intersection
    (`Subgraph_133/135/138` and the four of step 5). `ClipPaths` reads the cutter as the secondary
    input's `Polygon2D` data turned into a closed spline, and a polygon's boundary ring is the same
    set for a cut, so the ring alone is what this needs.

    `ClipPaths` clips against the UNION of `rings`, and the two directions compose differently:

    - Intersection keeps what any ring holds, so the per-ring clips are collected: chaining them
      would empty the result at the first ring the path misses, which for a road and 334 scattered
      intersection planes is every path.
    - Difference removes what any ring holds, so the clips are applied one ring at a time, each fed
      the previous call's output; collecting those instead would hand back spans a later ring had
      already removed."""
    if not paths:
        return []
    rings = [_ring_of(r) for r in rings]
    out = []
    for path in paths:
        if len(path) < 2:
            continue
        if inside:
            # `ClipPaths` keeps what the union holds, so one ring's spans and the next ring's must be
            # united along the path rather than simply concatenated: two overlapping planes would
            # otherwise contribute the same stretch of road twice.
            pieces = _union_spans(path, rings)
        else:
            pieces = [list(path)]
            for ring in rings:
                nxt = []
                for piece in pieces:
                    if len(piece) >= 2:
                        nxt += clip_path(piece, ring, keep_inside=False)
                pieces = nxt
                if not pieces:
                    break
        out += [p for p in pieces if len(p) >= 2 and path_length(p) > 0.0]
    return out


def _ring_of(r):
    if isinstance(r, Polygon):
        return list(r.outer)
    return list(r)


def _union_spans(path, rings):
    """The parts of `path` inside the union of `rings`, as `[path]`.

    Every ring is clipped separately and the surviving arclength intervals are merged, which is what
    `ClipPaths(Intersection)` computes against a union of cutters. Building it from the intervals
    rather than from the pieces keeps the merge exact, and it is the cheap direction: the rings of a
    road network overlap heavily (334 planes over 78 ribbons), so concatenating would count the same
    stretch of road several times and hand the grammar nodes more road than exists."""
    if not rings:
        return []
    cum = [0.0]
    for i in range(len(path) - 1):
        cum.append(cum[-1] + math.dist(path[i][:2], path[i + 1][:2]))
    total = cum[-1]
    if total <= 0.0:
        return []
    spans = []
    for ring in rings:
        for piece in clip_path(path, ring, keep_inside=True):
            if len(piece) < 2:
                continue
            a = _along(piece[0], path, cum)
            b = _along(piece[-1], path, cum)
            spans.append((min(a, b), max(a, b)))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        run = [_at_length(path, cum, a)]
        run += [tuple(path[k][:3]) for k in range(bisect.bisect_right(cum, a), bisect.bisect_left(cum, b))]
        run.append(_at_length(path, cum, b))
        out.append(run)
    return out


def _along(pt, path, cum):
    """The arclength position of `pt` on `path`, by projecting it onto every segment.

    A clip's ends lie ON the path but are usually not VERTICES of it -- `clip_path` inserts the
    crossing point into the piece. Snapping to the nearest vertex therefore collapses most spans:
    on a 2-point path a clip end in the middle snaps to one of the two ends, so both ends of the
    span come back equal and the span is zero-length. That is what emptied 71 of the port's local
    inside pieces (measured 2026-10-17), so this must project, not snap."""
    best, at = None, 0.0
    for i in range(len(path) - 1):
        ax, ay = path[i][0], path[i][1]
        bx, by = path[i + 1][0], path[i + 1][1]
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        t = 0.0 if seg == 0.0 else max(0.0, min(1.0,
            ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / seg))
        px, py = ax + t * dx, ay + t * dy
        d = (px - pt[0]) ** 2 + (py - pt[1]) ** 2
        if best is None or d < best:
            best, at = d, cum[i] + t * (cum[i + 1] - cum[i])
    return at


def _at_length(path, cum, s):
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    z = path[0][2] if len(path[0]) > 2 else 0.0
    return (path[i][0] + t * (path[i + 1][0] - path[i][0]),
            path[i][1] + t * (path[i + 1][1] - path[i][1]), z)



def minus(rings, cutters, ops):
    """`Compose_Areas_Exclusion` / `Polygon2DOperation(Difference)` of two polygon lists."""
    if not rings:
        return []
    if not cutters:
        return list(rings)
    a = [r for p in rings for r in [p.outer] + list(p.holes)]
    b = [r for p in cutters for r in [p.outer] + list(p.holes)]
    return ops.difference(a, b)


def union(groups, ops):
    """`Compose_Areas_Union` over a list of polygon lists.

    One ring with no holes needs no boolean -- the primitive's CoreProcess filters to Polygon2D and
    runs `Polygon2DOperation(Union)`, which for a single input returns it -- and routing it through
    Clipper2 only adds quantisation, so it is wrapped instead."""
    rings, holed = [], False
    for group in groups:
        for p in group:
            rings.append(p.outer)
            holed = holed or bool(p.holes)
            rings += list(p.holes)
    if not rings:
        return []
    if len(rings) == 1 and not holed:
        return [Polygon(list(rings[0]))]
    return ops.union(rings)


def solve(classes, params, ops):
    """The whole primitive.

    `classes` is `{class_tag: [path]}`; `params` needs the three widths plus optionally
    `intersection_expansion_range` and `roadSectionLimit`. Returns

      sections  {class_tag: [(path, label)]}  the primitive's three section outputs, flat and
                                              labelled `roadSections` / `intersections` /
                                              `intersectionsShort` the way `Gather_0/1/2` collect them
      planar    [Polygon]                     `IntersectionsPlanar`
      cutter    [Polygon]                     `Subgraph_124` (kept for the tests and the note)
      footprints [Polygon]                    the primitive's own `RoadsFootprints` (unused at stage
                                              level; the footprint half computes the published one)
    """
    widths = {tag: float(params[WIDTH_PARAM[tag]]) for tag in CLASSES}
    expand = float(params.get("intersection_expansion_range", EXPANSION_RANGE))
    limit = float(params.get("roadSectionLimit", SECTION_LIMIT))

    # 1 + 2: extend and outline each class plain.
    extended, plain = {}, {}
    for tag in CLASSES:
        extended[tag] = [extend(p, 0.5 * widths[tag]) for p in classes.get(tag, [])]
        plain[tag] = outline_class(extended[tag], widths[tag], ops)

    # 3: the expanded intersection planes.
    planes = intersection_planes([p for tag in CLASSES for p in plain[tag]], expand, ops)

    # 5 + 4: the +/-Y ribbons per class, and the cutter they build. The subtraction order is the
    # graph's: artery whole, collector minus artery, local minus artery and collector.
    artery_side = side_ribbons(extended[ARTERY], widths[ARTERY], planes, ops)
    collector_side = side_ribbons(extended[COLLECTOR], widths[COLLECTOR], planes, ops)
    local_side = side_ribbons(extended[LOCAL], widths[LOCAL], planes, ops)
    collector_only = minus(collector_side, plain[ARTERY], ops)
    local_only = minus(minus(local_side, plain[ARTERY], ops), plain[COLLECTOR], ops)
    cutter = union([artery_side, collector_only, local_only], ops)

    # 6 + 7 + 8: sections, labels and the planar set.
    sections, planar_parts = {}, {}
    for tag in CLASSES:
        outside = cut_paths(extended[tag], cutter, ops, False)
        inside = cut_paths(extended[tag], cutter, ops, True)
        long_out = [p for p in outside if path_length(p) > limit]
        short_out = [p for p in outside if path_length(p) <= limit]
        short_in = [p for p in inside if path_length(p) <= limit]
        sections[tag] = ([(p, "roadSections") for p in long_out]
                         + [(p, "intersections") for p in inside]
                         + [(p, "intersectionsShort") for p in short_out + short_in])
        # `Subgraph_148/145/149` outline the SHORT and the INSIDE data; the long sections between
        # intersections are the road, not an intersection, so they are not in the planar set.
        planar_parts[tag] = outline_class(short_out + inside, widths[tag], ops)
    return {"sections": sections,
            "planar": union([planar_parts[tag] for tag in CLASSES], ops),
            "cutter": cutter,
            "footprints": union([plain[tag] for tag in CLASSES], ops)}
