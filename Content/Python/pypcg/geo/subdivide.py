"""Area subdivision shared by Districts and Lots: AutoSplitPolygon (Subdivide_Areas_WithRecursiveSplit)
and the grid of Subdivide_Areas_withGrid (spike report, 2026-10-15). ops supplies cut_with_paths."""
from .plane import at, clip_path, frame_box, signed_area, split_frame

SLIVER_CM2 = 1.0e4                # pieces under 1 m2 are boolean noise and never output


def auto_split(ring, ratio, ops):
    """Cut ring with a line across its longest edge at `ratio` of the way back along it.
    Returns (pieces, [the cut clipped to ring])."""
    o, X, Y, u0, u1, w0, w1 = split_frame(ring)
    u, wc, hw = u1 - ratio * (u1 - u0), 0.5 * (w0 + w1), 2.0 * (w1 - w0)       # 4 x half-depth
    line = [at(o, X, Y, u, wc + hw), at(o, X, Y, u, wc - hw)]
    # CreateSpline -> ConvertSplineToPolyLine always halves a curve segment, so the cutting path
    # carries its midpoint; it survives as one collinear vertex per piece.
    cut = [line[0], at(o, X, Y, u, wc), line[1]]
    pieces = [r for r in ops.cut_with_paths(ring, [cut]) if abs(signed_area(r)) >= SLIVER_CM2]
    return pieces, clip_path(line, ring)


def recursive_split(ring, ops, iterations, min_area_cm2, ratio_fn, areas, paths, depth=0):
    """Split until `iterations` levels or until a piece is not larger than min_area_cm2; ratio_fn(ring)
    gives each split's ratio. A cut that does not divide the ring (fewer than 2 real pieces) keeps it whole."""
    if depth >= iterations or not abs(signed_area(ring)) > min_area_cm2:
        areas.append(ring)
        return
    pieces, cut = auto_split(ring, ratio_fn(ring), ops)
    if len(pieces) < 2:
        areas.append(ring)
        return
    paths.extend(cut)
    for r in pieces:
        recursive_split(r, ops, iterations, min_area_cm2, ratio_fn, areas, paths, depth + 1)


def grid_lines(ring, width, length, extend=100000.0):
    """[("X" | "Y", segment)]: lines across the longest-edge frame every `width` (X, perpendicular
    to the edge) and every `length` (Y, parallel to it), clipped to the ring."""
    o, X, Y, u0, u1, w0, w1 = frame_box(ring)
    out = []
    for axis, lo, hi, step in (("X", u0, u1, width), ("Y", w0, w1, length)):
        n = int((hi - lo) / step + 2)         # CreatePointsGrid(CellCorners), extents = half box + one cell
        for i in range(2, n + 1):             # FilterDataByIndex drops partitions 0 and 1
            c = lo + (i - 1) * step
            line = ([at(o, X, Y, c, w0 - extend), at(o, X, Y, c, w1 + extend)] if axis == "X" else
                    [at(o, X, Y, u0 - extend, c), at(o, X, Y, u1 + extend, c)])
            out += [(axis, seg) for seg in clip_path(line, ring)]
    return out
