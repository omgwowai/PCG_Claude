"""V1 checks of stage 6, Districts, with the editor's booleans (spec 3, V1).

check() verifies four invariants on every recorded run:
  - each area sits in the class its size says;
  - the areas add up to the City (the cut and the split lose nothing);
  - no two areas overlap;
  - every local road lies in a gridded district.
When the volume holds its official output, it also runs the oracle: it recovers the official split
ratios from the official collector roads and requires the Python cut, split, classes and grids to
match the official areas to 0.05 m2 and the official road lengths to 0.01 % (spike report, table 1)."""
import math

from pypcg import geo
from pypcg.stages import s06_districts as S

AREA_TAGS = ("UndividableDistricts", "SmallDistricts", "MediumDistricts", "LargeDistricts")
ROAD_TAGS = ("ArteryRoads", "CollectorRoads", "localRoads")


def _rings(outputs):
    return [(t, p.outer) for t in AREA_TAGS for p, _ in outputs.get(t, [])]


def _mid(spline):
    pts = spline.polyline or spline.points
    a, b = pts[0], pts[-1]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _length(spline):
    """The spline's length as the engine measures it. A curved spline is longer than its control-point
    polyline -- the City outline is 6213.2 m as a curve and 5945.4 m through its 9 control points -- so
    measure the dense polyline when the value carries one (every recorded input does), and the control
    points otherwise."""
    pts = list(spline.polyline or spline.points)
    return geo.path_length(pts + pts[:1] if spline.closed else pts)


def oracle_ratio(collectors):
    """ratio(ring) recovered from the official collector roads: the official split line of a ring is
    the collector whose midpoint lies inside it (spike: 6 of 6 recovered)."""
    def ratio(ring):
        for c in collectors:
            m = _mid(c)
            if geo.inside(m, ring):
                o, X, Y, u0, u1, w0, w1 = geo.split_frame(ring)
                u = (m[0] - o[0]) * X[0] + (m[1] - o[1]) * X[1]
                return (u1 - u) / (u1 - u0)
        return 0.5
    return ratio


def check(inputs, params, outputs, ops, official=None):
    f = []
    rings = _rings(outputs)
    for t, r in rings:
        want = S.classify(abs(geo.signed_area(r)) / 1e4, params)
        if want != t:
            f.append("an area of %.0f m2 is %s, its size says %s" % (abs(geo.signed_area(r)) / 1e4, t, want))
    if inputs:
        city = sum(abs(geo.signed_area(geo.ccw(S.ring_of(v)))) for v, _ in inputs["City"] if v.closed)
        total = sum(abs(geo.signed_area(r)) for _, r in rings)
        if city and not rings:
            f.append("the City has %.6g m2 and the outputs hold no area piece at all" % (city / 1e4,))
        elif city and abs(total - city) > 1e-4 * city:
            f.append("areas add up to %.6g m2, the City is %.6g m2" % (total / 1e4, city / 1e4))
    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            overlap = sum(geo.area_m2(p) for p in ops.intersection([rings[i][1]], [rings[j][1]]))
            if overlap > 1.0:
                f.append("areas %d and %d overlap by %.1f m2" % (i, j, overlap))
    gridded = [r for t, r in rings if t != "UndividableDistricts"]
    for line, _ in outputs.get("localRoads", []):
        if not any(geo.inside(_mid(line), r) for r in gridded):
            f.append("a local road at %s lies in no gridded district" % (tuple(round(c) for c in _mid(line)),))
            break
    if inputs and official and official.get("CollectorRoads"):
        f += _oracle(inputs, params, ops, official)
    return f


def _oracle(inputs, params, ops, official):
    f = []
    again = S.districts(inputs, params, ops, oracle_ratio(official["CollectorRoads"]))
    for t in AREA_TAGS:
        mine = sorted(abs(geo.signed_area(p.outer)) / 1e4 for p, _ in again[t])
        theirs = sorted(geo.area_m2(p) for p in official.get(t, []))
        if len(mine) != len(theirs) or any(abs(a - b) > 0.05 for a, b in zip(mine, theirs)):
            f.append("oracle %s: areas %s vs official %s" % (t, [round(a, 1) for a in mine], [round(b, 1) for b in theirs]))
    for t in ROAD_TAGS:
        mine = sum(_length(s) for s, _ in again[t])
        theirs = sum(_length(s) for s in official.get(t, []))
        if len(again[t]) != len(official.get(t, [])) or (theirs and abs(mine - theirs) > 1e-4 * theirs):
            f.append("oracle %s: %d roads %.1f m vs official %d roads %.1f m"
                     % (t, len(again[t]), mine / 100, len(official.get(t, [])), theirs / 100))
    return f
