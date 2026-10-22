"""V1 checks of stage 5, CentralParkFootprint (spec 3, V1).

The stage publishes one closed four-vertex spline from the volume's own transform, at Z 0. Every
clause is about that spline alone:

  - exactly one `Footprint`, closed, linear, four control points, all at Z 0 (the official graph's
    `AttributeMathsOp_0` sets `$Position.Z` to 0; the volume itself sits at Z 9950 in the demo);
  - the area is `RectWidth x RectLength` to AREA_TOL;
  - the corners are the four of a rectangle of those sides at the volume's yaw. This is measured:
    each corner is turned BACK by the yaw about the centre and must then sit at
    `(+-RectWidth / 2, +-RectLength / 2)` to CORNER_TOL_CM. Side lengths and area are both
    rotation-invariant, so without this clause a wrong yaw would pass every other number;
  - the signed area is NEGATIVE (the official order, traps.md 41).

The yaw measure is a MODULO-90 comparison, not an equality on one corner's angle: a rectangle is
invariant under a half turn and (when `RectWidth == RectLength`) under a quarter turn, so "corner 0
sits at yaw" is not a property of the shape. Requiring that every corner lands on an axis-aligned
corner of the right half-extents after the inverse rotation is symmetric-safe and still fails a
wrong yaw: a local corner `(W/2, L/2)` turned by `delta` lands `(W/2 - L/2) sin(delta)` off in X, so
the 0.5 cm bound fires at about a 6e-5 rad (0.0034 deg) error.

The oracle compares the vertex list to the official output element for element when the volume holds
its official graph; the demo's park is a measured fixture, so an order, a yaw or a sign mistake
fails at half a centimetre.

An EMPTY `Footprint` returns no failures on purpose: with no volume point the stage publishes no
output, and `test_empty_inputs_give_empty_outputs` in `Tools/pypcg/tests/test_s04_s05.py` is what
pins that behaviour off-line.
"""
import math

from pypcg import geo
from pypcg.stage_api import volume_point
from pypcg.stages import s05_central_park_footprint as S

AREA_TOL = 1e-6
VERTEX_TOL_CM = 0.5
SIDE_TOL_CM = 0.5
CORNER_TOL_CM = 0.5


def _splines(outputs):
    return [v for v in geo.values(outputs.get("Footprint", [])) if hasattr(v, "points")]


def check(inputs, params, outputs, ops, official=None):
    f = []
    items = outputs.get("Footprint", [])
    lines = _splines(outputs)
    if not items:
        return f
    if len(items) != 1:
        f.append("%d Footprint items; the stage publishes one rectangle" % len(items))
    width = float(params.get("RectWidth", 100000.0))
    length = float(params.get("RectLength", 20000.0))
    loc, yaw = volume_point(inputs or {})
    ring = S.rectangle((loc[0], loc[1]), width, length, yaw) if loc is not None else None
    for line in lines:
        if not line.closed:
            f.append("the Footprint spline is not closed")
        if not line.linear:
            f.append("the Footprint spline is not linear; `CreateSpline_1` builds a linear one")
        pts = line.points
        if len(pts) != 4:
            f.append("the Footprint has %d control points, not 4" % len(pts))
            continue
        if any(p[2] != 0.0 for p in pts):
            f.append("a Footprint vertex is not at Z 0 (the official graph pins it there)")
        if ring is not None:
            worst = max(math.dist(p[:2], q) for p, q in zip(pts, ring))
            if worst > VERTEX_TOL_CM:
                f.append("a Footprint corner is %.2f cm from where the volume's own transform puts it"
                         % worst)
        a = [(p[0], p[1]) for p in pts]
        area = geo.signed_area(a)
        if area >= 0.0:
            f.append("the Footprint's signed area is %.6g, positive; the official order is negative "
                     "(traps.md 41)" % area)
        elif abs(abs(area) - width * length) > AREA_TOL * width * length:
            f.append("the Footprint's area is %.6g cm2; RectWidth x RectLength is %.6g"
                     % (abs(area), width * length))
        sides = sorted(math.dist(a[i], a[(i + 1) % 4]) for i in range(4))
        want_sides = sorted([width, width, length, length])
        if any(abs(s - w) > SIDE_TOL_CM for s, w in zip(sides, want_sides)):
            f.append("the Footprint's sides are %s; RectWidth %.0f and RectLength %.0f give %s"
                     % ([round(s, 2) for s in sides], width, length,
                        [round(s, 2) for s in want_sides]))
        if loc is not None:
            f += _corners_at_yaw(a, yaw, width, length)
        if official and official.get("Footprint"):
            f += _oracle(a, official["Footprint"])
    return f


def _corners_at_yaw(ring, yaw, width, length):
    """Every corner, turned back by `yaw`, lands on an axis-aligned corner of the right half-extents.
    A modulo-90 comparison: see the module docstring for why an angle equality is wrong."""
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    worst, where = 0.0, None
    for p in ring:
        lx, ly = geo.rotate((p[0] - cx, p[1] - cy), -yaw)
        off = max(abs(abs(lx) - width / 2.0), abs(abs(ly) - length / 2.0))
        if off > worst:
            worst, where = off, p
    if worst > CORNER_TOL_CM:
        return ["a Footprint corner is %.2f cm off the axis-aligned corner of RectWidth x RectLength "
                "when turned back by the volume's yaw %.4f deg (corner %.1f, %.1f)"
                % (worst, yaw, where[0], where[1])]
    return []


def _oracle(mine, theirs):
    """The vertex list against the official one, in order: same count, same winding, each vertex
    within VERTEX_TOL_CM."""
    f = []
    for other in theirs:
        if not hasattr(other, "points"):
            continue
        b = [(p[0], p[1]) for p in other.points]
        if len(mine) != len(b):
            f.append("oracle Footprint: %d vertices vs official %d" % (len(mine), len(b)))
            return f
        if (geo.signed_area(mine) >= 0) != (geo.signed_area(b) >= 0):
            f.append("oracle Footprint: winding %s, official %s"
                     % ("ccw" if geo.signed_area(mine) >= 0 else "cw",
                        "ccw" if geo.signed_area(b) >= 0 else "cw"))
        worst = max(math.dist(p, q) for p, q in zip(mine, b))
        if worst > VERTEX_TOL_CM:
            f.append("oracle Footprint: a vertex is %.2f cm from the official one" % worst)
        return f
    return f
