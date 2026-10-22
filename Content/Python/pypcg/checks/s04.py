"""V1 checks of stage 4, MainTowerFootprint (spec 3, V1).

The stage publishes one closed hexagonal spline from the volume's own transform, so every clause is
about that spline alone:

  - exactly one `Footprint`, closed, linear, six control points, at the volume's Z;
  - every vertex sits at the distance from the centre that the geometry says it must: the two on the
    hexagon's local X axis at `RectWidth / 2`, the other four at
    `RectWidth / 2 x sqrt(1/4 + 3 (RectLength / RectWidth)^2 / 4)` -- see `S.radii`, which derives the
    two radii instead of reading them back from the builder (at `RectLength == RectWidth` all six
    are equal and this clause cannot tell a ratio error from none, which is the one shape the demo
    measures);
  - the signed area is the analytic `3 sqrt(3) / 2 R^2 x (Length / Width)` and NEGATIVE (the official
    order, traps.md 41);
  - with the volume's point available, every vertex sits where `ngon` puts it for that volume.

The oracle compares the vertex list to the official output element for element when the volume holds
its official graph: the two measured fixtures are the demo's own hexagon and the same one moved,
turned and stretched, so an order or a sign mistake fails rather than rounding into a tolerance.

An EMPTY `Footprint` returns no failures on purpose: with no volume point the stage publishes no
output, and `test_empty_inputs_give_empty_outputs` in `Tools/pypcg/tests/test_s04_s05.py` is what
pins that behaviour off-line.
"""
import math

from pypcg import geo
from pypcg.stage_api import volume_point
from pypcg.stages import s04_main_tower_footprint as S

AREA_TOL = 1e-6            # the analytic area is exact up to float rounding (relative)
VERTEX_TOL_CM = 0.5        # the official vertices are recorded to 4 decimals; 0.1 cm was measured


def _splines(outputs):
    return [v for v in geo.values(outputs.get("Footprint", [])) if hasattr(v, "points")]


def check(inputs, params, outputs, ops, official=None):
    f = []
    items = outputs.get("Footprint", [])
    lines = _splines(outputs)
    if not items:
        return f
    if len(items) != 1:
        f.append("%d Footprint items; the stage publishes one hexagon" % len(items))
    width = float(params.get("RectWidth", 16000.0))
    length = float(params.get("RectLength", 16000.0))
    loc, yaw = volume_point(inputs or {})
    ring = S.hexagon((loc[0], loc[1]), width, length, yaw) if loc is not None else None
    want_radii = S.radii(width, length)
    for line in lines:
        if not line.closed:
            f.append("the Footprint spline is not closed")
        if not line.linear:
            f.append("the Footprint spline is not linear; `CreateSpline_1` builds a linear one")
        pts = line.points
        if len(pts) != S.N:
            f.append("the Footprint has %d control points, not %d" % (len(pts), S.N))
            continue
        if loc is not None and any(abs(p[2] - loc[2]) > 1e-6 for p in pts):
            f.append("a Footprint vertex is not at the volume's Z %.4f" % loc[2])
        if ring is not None:
            worst = max(math.dist(p[:2], q) for p, q in zip(pts, ring))
            if worst > VERTEX_TOL_CM:
                f.append("a Footprint vertex is %.2f cm from where the volume's own transform puts it"
                         % worst)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for i, (p, want) in enumerate(zip(pts, want_radii)):
            got = math.dist((p[0], p[1]), (cx, cy))
            if abs(got - want) > VERTEX_TOL_CM:
                f.append("vertex %d is %.2f cm from the centre; RectWidth %.0f / RectLength %.0f put "
                         "it at %.2f" % (i, got, width, length, want))
                break
        area = geo.signed_area([(p[0], p[1]) for p in pts])
        want = -3.0 * math.sqrt(3.0) / 2.0 * (width / 2.0) ** 2 * (length / width if width else 1.0)
        if area >= 0.0:
            f.append("the Footprint's signed area is %.6g, positive; the official order is negative "
                     "(traps.md 41)" % area)
        elif abs(area - want) > AREA_TOL * abs(want):
            f.append("the Footprint's signed area is %.6g cm2; the analytic hexagon is %.6g"
                     % (area, want))
        if official and official.get("Footprint"):
            f += _oracle(pts, official["Footprint"])
    return f


def _oracle(mine, theirs):
    """The vertex list against the official one, in order: same count, same winding, each vertex
    within VERTEX_TOL_CM. An order or a sign error moves vertices by kilometres."""
    f = []
    for other in theirs:
        if not hasattr(other, "points"):
            continue
        a = [(p[0], p[1]) for p in mine]
        b = [(p[0], p[1]) for p in other.points]
        if len(a) != len(b):
            f.append("oracle Footprint: %d vertices vs official %d" % (len(a), len(b)))
            continue
        if (geo.signed_area(a) >= 0) != (geo.signed_area(b) >= 0):
            f.append("oracle Footprint: winding %s, official %s"
                     % ("ccw" if geo.signed_area(a) >= 0 else "cw",
                        "ccw" if geo.signed_area(b) >= 0 else "cw"))
        worst = max(math.dist(p, q) for p, q in zip(a, b))
        if worst > VERTEX_TOL_CM:
            f.append("oracle Footprint: a vertex is %.2f cm from the official one" % worst)
        return f
    return f
