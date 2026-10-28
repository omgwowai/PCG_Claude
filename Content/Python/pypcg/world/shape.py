"""Shape measures of polylines (the river, roads and streets), for the stages' summaries, the tests and the offline
plan tool (Tools/pyworld/offline.py). Pure."""
from . import geom

STRAIGHT_RADIUS = 150000.0       # a stretch flatter than a 1.5 km radius counts as straight
STEP = 500.0                     # measured on the line resampled every 5 m


def curvature(pts):
    """Signed curvature (1/cm) at every point (circle through the neighbours; an end point takes its neighbour's)."""
    if len(pts) < 3:
        return [0.0] * len(pts)
    out = [0.0]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        ab, bc, ca = geom.dist2d(a, b), geom.dist2d(b, c), geom.dist2d(c, a)
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        out.append(2.0 * cross / (ab * bc * ca) if ab * bc * ca > 0.0 else 0.0)
    out.append(out[-1])
    out[0] = out[1]
    return out


def straight_runs(pts, step=STEP, radius=STRAIGHT_RADIUS):
    """Lengths (cm) of the stretches where the line, resampled every `step`, bends less than a `radius` circle."""
    rs = geom.resample([p[:2] for p in pts], step)
    k = curvature(rs)
    runs, cur = [], 0.0
    for i in range(1, len(rs)):
        if abs(k[i]) < 1.0 / radius:
            cur += geom.dist2d(rs[i - 1], rs[i])
        elif cur:
            runs.append(cur)
            cur = 0.0
    if cur:
        runs.append(cur)
    return runs


def max_turn(pts, step=STEP):
    """Largest heading change (degrees) between consecutive `step` segments: a kink in the line shows as a jump."""
    rs = geom.resample([p[:2] for p in pts], step)
    out = 0.0
    for a, b, c in zip(rs, rs[1:], rs[2:]):
        out = max(out, abs((geom.yaw_deg(b, c) - geom.yaw_deg(a, b) + 180.0) % 360.0 - 180.0))
    return out


def stats(pts, step=STEP):
    """{length_m, sinuosity, straight_share, longest_straight_m, max_turn_deg, min_radius_m} of a polyline."""
    rs = geom.resample([p[:2] for p in pts], step)
    total = geom.length(rs)
    if len(rs) < 3 or total <= 0.0:
        return {"length_m": total / 100.0, "sinuosity": 1.0, "straight_share": 1.0, "longest_straight_m": total / 100.0,
                "max_turn_deg": 0.0, "min_radius_m": 1e9}
    runs = straight_runs(rs, step)
    k = max(abs(x) for x in curvature(rs))
    chord = geom.dist2d(rs[0], rs[-1]) or 1.0
    return {"length_m": total / 100.0, "sinuosity": total / chord, "straight_share": sum(runs) / total,
            "longest_straight_m": max(runs, default=0.0) / 100.0, "max_turn_deg": max_turn(rs, step),
            "min_radius_m": (1.0 / k if k > 0.0 else 1e9) / 100.0}


def overlap_length(a, b, tol=300.0, step=STEP):
    """Length (cm) of polyline a that runs within `tol` of polyline b: two roads laid on top of each other."""
    idx = geom.SegmentIndex(2000.0)
    idx.add_polyline([p[:2] for p in b])
    rs = geom.resample([p[:2] for p in a], step)
    out = 0.0
    for p, q in zip(rs, rs[1:]):
        m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if idx.nearest(m[0], m[1], tol) is not None:
            out += geom.dist2d(p, q)
    return out
