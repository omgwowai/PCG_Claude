"""V1 checks of stage 14, Parkings (spec 3, V1).

The main node's inputs are the stage-13 lots alone -- polygons, recordable -- so V1 REPLAYS each run record
whole (`pypcg_v1_editor.py`: same seed, field for field) and then calls `check`. The terrain is read only by
the second node, `s14_parkings_finish`, whose record (`s14_finish.json`) V1 does not replay (trap 60).

`check(inputs, params, outputs, ops, official)` -- the task's invariants, on the record's outputs and on the
intermediates the stage's own functions rebuild from the record's inputs with the editor's booleans:

  - empty inputs -> every output empty;
  - every space centre lies inside the footprint (within `INSIDE_TOL_CM`);
  - the number of spaces is the number of 350 cm segments of the space lines, `sum(int(L / 350) - 1)` over
    every resampled line -- the brief's "within 10 % of area / space area" is not what the official graph
    computes (s14.md 5.1: 733 official spaces on 42 100 m2 is 57 m2 a space, the aisles, medians and the
    outer band taking the rest); this one is exact;
  - one parking line decal per space-line control point, and every car on an occupied space: a forward car
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


def check(inputs, params, outputs, ops, official=None):
    fails = []
    if inputs is None:
        return ["no recordable inputs: stage 14's main node reads polygons only, so a record always has them"]
    lots, rows, spaces, bands = rebuild(inputs, ops)
    if not lots:
        busy = [pin for pin in S.OUTPUTS if outputs.get(pin)]
        return ["empty footprint but outputs on %s" % busy] if busy else []

    # spaces: inside the footprint, and exactly the 350 cm segments of the space lines
    out_of = [i for i, p in enumerate(spaces.loc) if not _in_lots(p, lots)]
    if out_of:
        fails.append("%d of %d space centres outside the footprint (first %s)" % (len(out_of), len(spaces), out_of[:3]))
    want = sum(max(len(r) - 1, 0) for r in rows)
    if len(spaces) != want:
        fails.append("%d spaces, but the space lines hold %d segments" % (len(spaces), want))
    # a resampled line's own length can sit a hair either side of a multiple of 350 cm (the 35.0 m aisles do)
    bad = [i for i, r in enumerate(rows)
           if len(r) not in {int((SP.length(r) - 1e-6) / S.SPACE_CM), int((SP.length(r) + 1e-6) / S.SPACE_CM)}]
    if bad:
        fails.append("%d space lines do not hold int(L / 350) points" % len(bad))

    # line decals: one per control point of the space lines
    n_lines = sum(len(v) for v, _t in outputs.get("Lines", []))
    if n_lines != sum(len(r) for r in rows):
        fails.append("%d line decals for %d space-line control points" % (n_lines, sum(len(r) for r in rows)))

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
