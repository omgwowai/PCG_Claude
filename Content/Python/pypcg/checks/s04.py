"""V1 checks of stage 4, MainTowerFootprint (spec 3, V1).

The stage publishes one closed hexagonal spline from the volume's own transform, so every clause is
about that spline alone:

  - exactly one `Footprint`, closed, linear, six control points, at the volume's Z;
  - every vertex is `RectWidth / 2` from the centre across the flats' axis and `RectLength / 2 x
    sqrt(3) / 2` along it (the hexagon's two radii), i.e. the shape has the size the parameters say;
  - the signed area is the analytic `3 sqrt(3) / 2 R^2 x (Length / Width)` and NEGATIVE (the official
    order, traps.md 41);
  - with the volume's point available, every vertex sits where `ngon` puts it for that volume.

The oracle compares the vertex list to the official output element for element when the volume holds
its official graph: the two measured fixtures are the demo's own hexagon and the same one moved,
turned and stretched, so an order or a sign mistake fails rather than rounding into a tolerance.
"""
import math

from pypcg import geo
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
    loc, yaw = S.volume_point(inputs or {})
    ring = S.hexagon((loc[0], loc[1]), width, length, yaw) if loc is not None else None
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
        r_flat = min(math.dist((p[0], p[1]), (cx, cy)) for p in pts)
        r_corner = max(math.dist((p[0], p[1]), (cx, cy)) for p in pts)
        # Across the flats the hexagon is 2r; corner to corner it is 2 R with R the circumradius, so
        # the two radii are Width / 2 and (Width / 2) x Length / Width.
        if abs(r_flat - width / 2.0) > 0.5:
            f.append("the hexagon's inradius is %.2f cm; RectWidth %.0f / 2 = %.2f"
                     % (r_flat, width, width / 2.0))
        want_corner = width / 2.0 * length / width if width else width / 2.0
        if abs(r_corner - want_corner) > 0.5:
            f.append("the hexagon's circumradius is %.2f cm; RectWidth/2 x Length/Width = %.2f"
                     % (r_corner, want_corner))
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
