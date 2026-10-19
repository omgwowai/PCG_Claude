"""V1 checks of stage 14, Parkings (spec 3, V1).

The main node's inputs are the stage-13 lots alone -- polygons, recordable -- so V1 REPLAYS each run record
whole (`pypcg_v1_editor.py`: same seed, field for field) and then calls `check`. The terrain is read only by
the second node, `s14_parkings_finish`, whose record (`s14_finish.json`) V1 does not replay (trap 60).

`check(inputs, params, outputs, ops, official)` -- the task's invariants, on the record's outputs and on the
intermediates the stage's own functions rebuild from the record's inputs with the editor's booleans:

  - empty inputs -> every output empty;
  - every space centre lies inside the footprint (within `INSIDE_TOL_CM`);
  - the space COUNT and the decal count against what does not pass through the resampler: the RECORDED
    `CentralLines` (two rows each) and the outer pieces before their resample, each line holding `int(L / 350)`
    points (none under two) with this module's own 350 cm, +-1 per line whose length is within 1e-6 of a multiple
    of 350 (on the demo level eleven 35.0 m aisles sit there: +-22); and every space line evenly spaced at >= 350 cm.
    Two CONSISTENCY clauses besides: one space per space-line segment, and the recorded decals equal the rebuilt
    control points exactly (the clause that sees a single dropped decal). The brief's "within 10 % of area / space
    area" is not what the official graph computes (s14.md 5.1: 57 m2 of lot per space);
  - one space per space-line segment, and every car on an occupied space: a forward car
    exactly on a space centre, a reversed one within 50 cm of one (`Subgraph_5`'s random Y range), each
    facing one of the two ways -- the space's yaw +90 (forward) or -90 (reversed), within the 5 degree random
    range -- and no two cars on one space;
  - the entrance cut leaves a gap: every lot crossed by a median band has a border shorter than its perimeter;
  - every ground tile centre lies inside a lot.
"""
import math

from pypcg import geo
from pypcg.geo import areas as A
from pypcg.geo import splines as SP
from pypcg.stages import s14_parkings as S

INSIDE_TOL_CM = 1.0
SPACE_CM = 350.0            # Subgraph_45 / 62 Distance: this module's own copy of the official value (the tests
                            # read it from the official IR), so a wrong spacing in the stage cannot hide here
CAR_YAW_TOL_DEG = 5.0 + 1e-6
CAR_OFFSET_CM = 50.0 + 1e-6
SAME_CM = 1e-6


def _dist_to_ring(p, ring):
    from pypcg.checks.s10 import dist_to_ring
    return dist_to_ring(p, ring)


def _in_lots(p, lots, tol=INSIDE_TOL_CM):
    return any(geo.inside(p[:2], q.outer) or _dist_to_ring(p[:2], q.outer) <= tol for q in lots)


def _angle(a, b):
    d = (a - b) % 360.0
    return min(d, 360.0 - d)


def rebuild(inputs, ops):
    """The stage's own intermediates from its inputs: (lots, space lines, space centres, median bands)."""
    lots = S.lots_of(inputs)
    if not lots:
        return lots, [], geo.Points(), []
    outer = S.outer_areas(lots, ops)
    central = S.central_lines(S.aisles(S.grid_cells(S.inner_areas(outer, ops), ops), ops))
    bands = S.median_bands(S.medians(lots, ops), ops)
    row_a, row_b = S.inner_rows(central)
    rows = row_a + row_b + S.outer_lines(outer, bands, ops)
    return lots, rows, S.space_centres(rows), bands


def _cars(outputs, pin):
    pts = [v for v, _t in outputs.get(pin, []) if isinstance(v, geo.Points)]
    return pts[-1] if pts else geo.Points()        # a static-mesh Assign_Assets output is its moved targets


def _fit(length):
    """(points `Transform_Resample (Distance 350, FitToCurve)` gives a line of `length`: int(L / 350), none under
    two; whether L is within 1e-6 of a multiple of 350, where the count can fall either side)."""
    n = int(length / SPACE_CM)
    q = length / SPACE_CM
    return (n if n >= 2 else 0), int(abs(q - round(q)) < 1e-6)


def _even(path):
    d = [math.dist(path[i][:2], path[i + 1][:2]) for i in range(len(path) - 1)]
    return min(d) >= SPACE_CM - 1e-6 and max(d) - min(d) <= 1e-6 and max(d) < 3 * SPACE_CM


def outer_pieces(lots, bands, ops):
    """The outer band's lines BEFORE their resample (`Subgraph_36` -> `43` -> `44` -> `61`)."""
    runs = [SP.chord(SP.truncate(r, S.OUTER_TRUNC_CM, S.OUTER_TRUNC_CM)) for r in S._runs(S.outer_areas(lots, ops))]
    return S._cut(runs, bands, ops)


def check(inputs, params, outputs, ops, official=None):
    fails = []
    if inputs is None:
        return ["no recordable inputs: stage 14's main node reads polygons only, so a record always has them"]
    lots, rows, spaces, bands = rebuild(inputs, ops)
    if not lots:
        busy = [pin for pin in S.OUTPUTS if outputs.get(pin)]
        return ["empty footprint but outputs on %s" % busy] if busy else []

    # spaces: inside the footprint
    out_of = [i for i, p in enumerate(spaces.loc) if not _in_lots(p, lots)]
    if out_of:
        fails.append("%d of %d space centres outside the footprint (first %s)" % (len(out_of), len(spaces), out_of[:3]))

    # the space COUNT, from what does not go through the resampler: the RECORDED centre lines (two rows each) and
    # the outer pieces before their resample, each holding int(L / 350) points -- the official rule, with this
    # module's own 350 cm. A length within 1e-6 of a multiple of 350 may land either side (the 35.0 m aisles do).
    want_spaces = want_points = tol = 0
    for v, _t in outputs.get("CentralLines", []):
        n, near = _fit(SP.length(v.points))
        want_spaces += 2 * max(n - 1, 0)
        want_points += 2 * n
        tol += 2 * near
    for piece in outer_pieces(lots, bands, ops):
        n, near = _fit(SP.length(piece))
        want_spaces += max(n - 1, 0)
        want_points += n
        tol += near
    if abs(len(spaces) - want_spaces) > tol:
        fails.append("%d spaces, but the recorded centre lines and the outer pieces hold %d 350 cm spaces (+-%d)"
                     % (len(spaces), want_spaces, tol))
    n_lines = sum(len(v) for v, _t in outputs.get("Lines", []))
    if abs(n_lines - want_points) > tol:
        fails.append("%d line decals, but the recorded centre lines and the outer pieces hold %d (+-%d)"
                     % (n_lines, want_points, tol))
    # the spacing itself: even along each line, and L / (N - 1) >= 350 cm with N = int(L / 350) >= 2
    uneven = [i for i, r in enumerate(rows) if len(r) >= 2 and not _even(r)]
    if uneven:
        fails.append("%d space lines are not evenly spaced at >= %.0f cm (first %d)" % (len(uneven), SPACE_CM, uneven[0]))
    if len(spaces) != sum(max(len(r) - 1, 0) for r in rows):           # consistency: one space per segment
        fails.append("%d spaces for %d space-line segments" % (len(spaces), sum(max(len(r) - 1, 0) for r in rows)))
    if n_lines != sum(len(r) for r in rows):                             # consistency: the record against the rebuild
        fails.append("%d recorded line decals for %d rebuilt space-line control points" % (n_lines, sum(len(r) for r in rows)))

    # cars: on occupied spaces, facing one of the two ways
    taken = set()
    for pin, sign, reach in (("ForwardCars", 90.0, SAME_CM), ("ReverseCars", -90.0, CAR_OFFSET_CM)):
        cars = _cars(outputs, pin)
        for j in range(len(cars)):
            loc, yaw = cars.loc[j], cars.rot[j][1]
            best = min(range(len(spaces)), key=lambda i: math.dist(spaces.loc[i][:2], loc[:2])) if len(spaces) else None
            if best is None or math.dist(spaces.loc[best][:2], loc[:2]) > reach:
                fails.append("%s %d at %s is on no space" % (pin, j, tuple(round(c, 1) for c in loc)))
                continue
            if _angle(yaw, spaces.rot[best][1] + sign) > CAR_YAW_TOL_DEG:
                fails.append("%s %d faces %.2f deg; its space %.2f deg %+d" % (pin, j, yaw, spaces.rot[best][1], sign))
            if best in taken:
                fails.append("%s %d shares space %d with another car" % (pin, j, best))
            taken.add(best)

    # the entrance cut: every lot crossed by a median band keeps a gap in its border
    border = [v.points for v, _t in outputs.get("Border", [])]
    for k, lot in enumerate(lots):
        crossed = any(A.intersection([lot], [b], ops) for b in bands) if bands else False
        mine = [p for p in border if p and _in_lots(SP.center([p[0], p[-1]])[0], [lot], 10.0)]
        perim = geo.path_length(list(lot.outer) + [lot.outer[0]])
        got = sum(SP.length(p) for p in mine)
        if crossed and not got < perim - 1.0:
            fails.append("lot %d: border %.1f cm of a %.1f cm perimeter -- no entrance gap" % (k, got, perim))

    # ground tiles inside a lot
    stray = sum(1 for v, _t in outputs.get("Tiles", []) for p in v.loc if not _in_lots(p, lots))
    if stray:
        fails.append("%d ground tiles outside every lot" % stray)
    return fails[:40]
