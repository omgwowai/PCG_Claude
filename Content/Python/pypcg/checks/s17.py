"""V1 checks of stage 17, CityEdge (spec 3, V1).

The recorded run's `MeshTerrain` input is 263 364 points, over `geo.MAX_RECORDED_POINTS`, so the record
keeps only a summary and V1 runs `check(None, ...)` -- as it does for the surface-input stages (trap
60): `replayed` is 0 and determinism is "the same-seed slim records are identical". What a check can
still see on the OUTPUT alone, and checks here:

  - the last `Docks` item is the docks themselves (the `Assign_Assets` primitive appends the moved
    targets): at least one, each carrying one of the five kit paths as `Asset`, roll and pitch zero;
  - moved back by the stage's own `PositionOffset`, the docks are a strictly convex polygon in the
    hull's own counter-clockwise order -- any subset of a convex polygon's vertices taken in order is
    one, so a dock off the hull, or out of order, shows here;
  - every other item is one kit's copies: its point count is a whole multiple of the number of docks
    that kit was assigned to, every copy carries an `Asset`, and there is one item per kit used.

With the inputs (offline, or a fixture), it also checks the task's invariants against the hull itself:
the dock count is `ceil(hull vertices x DockRatio)`, every dock is a hull vertex, and the hull contains
every kept terrain point."""
import math

from pypcg import geo
from pypcg.geo import assets as A
from pypcg.stages import s17_city_edge as S

ANGLE_TOL_DEG = 1e-6
VERTEX_TOL_CM = 1e-6


def _items(outputs):
    return [v for v in geo.values(outputs.get("Docks", [])) if isinstance(v, geo.Points)]


def unmoved(docks):
    """Each dock's hull vertex: the moved location minus `RotateVector(q, PositionOffset)`."""
    off = tuple(A._f32(x) for x in S.POSITION_OFFSET)
    out = []
    for i in range(len(docks)):
        q = tuple(docks.quat[i]) if docks.quat else A.quat_of(*docks.rot[i])
        d = geo.quat_rotate(q, off)
        out.append(tuple(docks.loc[i][a] - d[a] for a in range(3)))
    return out


def _convex_ccw(ring):
    """True when `ring` (>= 3 points) turns left at every vertex."""
    n = len(ring)
    for k in range(n):
        o, a, b = ring[k - 1], ring[k], ring[(k + 1) % n]
        if (a[0] - o[0]) * (b[1] - a[1]) - (a[1] - o[1]) * (b[0] - a[0]) <= 0.0:
            return False
    return True


def check(inputs, params, outputs, ops, official=None):
    f = []
    items = _items(outputs)
    if not items:
        if inputs is not None and any(len(v) and S.above(v, float(params["SeaLevel"]))
                                      for v in geo.values(inputs.get("MeshTerrain", []))
                                      if isinstance(v, geo.Points)):
            f.append("terrain points above sea level, but no Docks output")
        return f
    docks, kits = items[-1], items[:-1]
    paths = docks.attrs.get(A.ASSET_ATTR) or []
    if not len(docks):
        return ["the last Docks item (the docks) is empty"]
    bad = sorted({p for p in paths if p not in S.ASSETS})
    if bad:
        f.append("docks carry assets outside the five kits: %s" % bad[:3])
    for i, r in enumerate(docks.rot):
        if abs(r[0]) > ANGLE_TOL_DEG or abs(r[2]) > ANGLE_TOL_DEG:
            f.append("dock %d has pitch %.3g and roll %.3g; both are zeroed" % (i, r[0], r[2]))
            break
    verts = unmoved(docks)
    # Three docks or fewer prove nothing about convexity: a hull of <= 3 points passes through
    # `ConvexHull2D` in input order, which can be clockwise.
    if len(verts) > 3 and not _convex_ccw(verts):
        f.append("the %d docks, moved back by the offset, are not a convex ring in hull order" % len(verts))
    used = [p for p in S.ASSETS if p in paths]
    if len(kits) != len(set(paths)):
        f.append("%d kit items for %d kits used" % (len(kits), len(set(paths))))
    for item in kits:
        assets = item.attrs.get(A.ASSET_ATTR) or []
        if len(assets) != len(item) or any(a in (None, "") for a in assets):
            f.append("a kit item has points without an Asset")
    counts = sorted(paths.count(p) for p in used)
    if len(kits) == len(used) and kits:
        for item in kits:
            if not any(c and len(item) % c == 0 for c in counts):
                f.append("a kit item of %d points is not a whole number of copies of any kit's docks %s"
                         % (len(item), counts))
    if inputs is not None:
        f += _against_inputs(inputs, params, docks, verts)
    return f


def _against_inputs(inputs, params, docks, verts):
    f = []
    terrains = [v for v in geo.values(inputs.get("MeshTerrain", [])) if isinstance(v, geo.Points) and len(v)]
    if len(terrains) != 1:
        return f
    kept = S.above(terrains[0], float(params["SeaLevel"]))
    ring = S.hull_ring(kept)
    want = int(math.ceil(len(ring) * min(max(float(params["DockRatio"]), 0.0), 1.0)))
    if len(docks) != want:
        f.append("%d docks on a %d-vertex hull; ceil(%d x %.4f) is %d"
                 % (len(docks), len(ring), len(ring), float(params["DockRatio"]), want))
    on = [min(math.dist(v[:2], r[:2]) for r in ring) <= VERTEX_TOL_CM for v in verts]
    if not all(on):
        f.append("%d docks are not on a hull vertex" % on.count(False))
    xy = [(p[0], p[1]) for p in ring]
    if len(xy) > 3:
        for p in kept:
            if not _within(p, xy):
                f.append("the hull does not contain the kept point %s" % (p,))
                break
    return f


def _within(p, ring):
    """True when `p` is inside or on the counter-clockwise convex `ring`."""
    n = len(ring)
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < -1e-6:
            return False
    return True
