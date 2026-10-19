"""V1 checks of stage 10, Ground (spec 3, V1).

The stage reads the final mesh terrain, so its run record cannot be replayed whole (trap 60), and its
tile sets are over `geo.MAX_RECORDED_POINTS`, so the record keeps their sizes only. `check_record`
therefore does what a record still allows (`pypcg_v1_editor.py` calls it in place of `check` when a
checks module defines it):

  1. the PARTIAL REPLAY: the stage is run again on the record's own non-surface inputs, with its own
     seed, on a flat surface. Everything the terrain does not touch must come out identical -- every
     sidewalk segment, corner shape and railing zone field for field, and every tile set's size, tag
     and order (the seven-way split is the seeded part of the stage). The terrain fit itself is
     measured against the official primitive point for point instead (s10.md section 6);
  2. the task's invariants (`check`) on that replay, whose tile XY are the recorded run's (the fit
     moves a tile in Z and turns it, never in XY: measured bit for bit on 20 000 official tiles).

`check(inputs, params, outputs, ops)` is the invariants alone, for offline fixtures:

  - every tile centre lies in the ground area (Lots less the excluded areas) grown by `GROUND_EXPAND_CM`,
    and in the pedestrian area (the City grown by half the artery width);
  - no tile centre lies deeper than `GROUND_EXPAND_CM` inside an excluded area (the undividable
    districts, the small landmark park, the reserved lots): the official grows the buildable pieces by
    that much "for coverage under the sidewalk", so a tile may reach that far in and no further;
  - no tile centre lies inside the landmark footprint (`MainTower`, the one building footprint the
    stage reads -- the lots' own building footprints are tiled underneath by design, s10.md 5.2);
  - the seven tile meshes are all used (on a run of at least `ALL_SEVEN_MIN_PIECES` ground pieces), each
    tile set carries one of them, and the sets hold every tile;
  - every sidewalk segment runs along its source: its midpoint lies within `SEGMENT_TOL_CM` of a lot
    ring, of the grown City ring, or of the contracted landmark ring, and no interior vertex of a run
    turns by more than that source's cut angle;
  - the corner shapes are the boundary pieces, every lot and the contracted landmark; the railing zones
    sit inside the lots, 21 cm above them.

Two clauses are CONSISTENCY checks, not invariants: the tile count against the stage's own fill of the
ground pieces, and the segment count against the stage's own `segments_of` -- both rebuild the expected
value with the stage's functions, so they catch a broken assembly, not a wrong algorithm. The algorithm
is measured against the official graph instead (`Tools/pypcg/data/s10_official_measurements.json`).
"""
import math

from pypcg import geo
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stages import s10_ground as S

SEGMENT_TOL_CM = 100.0          # the brief's 1 m
# "The seven tile assets are all used across a run" holds with near certainty only on a city-sized
# run: with n pieces drawn one way each at 1/7, a way stays empty with probability <= 7 (6/7)^n --
# 1.7e-8 at the demo level's 129 pieces, 3.4e-6 at 100. Below that the clause is not asserted.
ALL_SEVEN_MIN_PIECES = 100
EDGE_EPS_CM = 1e-3


class _Flat:
    """A flat surface: the partial replay does not need heights, only the XY and the split."""

    kind = "flat"

    def height(self, x, y):
        return 0.0


def _dist_seg(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def dist_to_ring(p, ring, closed=True):
    n = len(ring)
    if n == 0:
        return float("inf")
    m = n if closed else n - 1
    return min(_dist_seg(p, ring[i], ring[(i + 1) % n]) for i in range(max(m, 1)))


class _Banded:
    """A polygon's rings with their edges bucketed in Y bands, so a point test reads only the edges that
    cross its row (the grown City ring has ~10^3 vertices, the run ~10^5 tiles)."""

    BAND = 500.0

    def __init__(self, poly):
        self.poly = poly
        self.bands = {}
        for ring in [poly.outer] + list(poly.holes):
            n = len(ring)
            for i in range(n):
                a, b = ring[i - 1], ring[i]
                lo, hi = min(a[1], b[1]), max(a[1], b[1])
                for k in range(int(math.floor(lo / self.BAND)), int(math.floor(hi / self.BAND)) + 1):
                    self.bands.setdefault(k, []).append((a, b))

    def contains(self, pt):
        x, y, c = pt[0], pt[1], False
        for (xj, yj), (xi, yi) in ((a[:2], b[:2]) for a, b in self.bands.get(int(math.floor(y / self.BAND)), [])):
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                c = not c
        return c


class _Index:
    """Polygons bucketed by a coarse grid, for point queries over ~10^5 tiles."""

    CELL = 5000.0

    def __init__(self, polys):
        self.cells = {}
        for p in polys:
            if len(p.outer) < 3:
                continue
            (x0, y0), (x1, y1) = geo.bbox(p.outer)
            fast = _Banded(p)
            for i in range(int(math.floor(x0 / self.CELL)), int(math.floor(x1 / self.CELL)) + 1):
                for j in range(int(math.floor(y0 / self.CELL)), int(math.floor(y1 / self.CELL)) + 1):
                    self.cells.setdefault((i, j), []).append(((x0, y0, x1, y1), p, fast))

    def _cands(self, pt, tol=0.0):
        seen = set()
        for i in range(int(math.floor((pt[0] - tol) / self.CELL)), int(math.floor((pt[0] + tol) / self.CELL)) + 1):
            for j in range(int(math.floor((pt[1] - tol) / self.CELL)), int(math.floor((pt[1] + tol) / self.CELL)) + 1):
                for box, p, fast in self.cells.get((i, j), []):
                    if id(p) not in seen:
                        seen.add(id(p))
                        yield box, p, fast

    def holders(self, pt):
        for (x0, y0, x1, y1), p, fast in self._cands(pt):
            if x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1 and fast.contains(pt):
                yield p

    def near(self, pt, tol):
        """True when pt is inside a polygon or within tol of its outer ring."""
        for (x0, y0, x1, y1), p, fast in self._cands(pt, tol):
            if x0 - tol <= pt[0] <= x1 + tol and y0 - tol <= pt[1] <= y1 + tol:
                if fast.contains(pt) or dist_to_ring(pt, p.outer) <= tol:
                    return True
        return False


def _midpoint(pts):
    L = geo.path_length(pts)
    s = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a[:2], b[:2])
        if s + d >= L / 2.0 and d > 0:
            t = (L / 2.0 - s) / d
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        s += d
    return tuple(pts[-1][:2])


def _turns(path):
    out = []
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu > 1e-9 and lv > 1e-9:
            out.append(math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv))))))
    return out


def _tiles(outputs):
    return [(v, t) for v, t in outputs.get("GroundTiles", []) if isinstance(v, geo.Points)]


def check(inputs, params, outputs, ops, official=None):
    f = []
    if inputs is None:
        return f
    src = S.read(inputs)
    tiles = _tiles(outputs)

    # ---- tiles ----
    if tiles:
        used = set()
        for v, tags in tiles:
            names = [t for t in tags if t.startswith("SM_Plaza_Square_")]
            assets = set(v.attrs.get(AS.ASSET_ATTR) or [])
            if len(names) != 1 or len(assets) != 1:
                f.append("a tile set carries %s / %s, not one plaza mesh" % (names, sorted(assets)))
                continue
            letter = names[0][-1]
            if assets != {S._MESH % (letter, letter)}:
                f.append("tile set %s carries %s" % (letter, sorted(assets)))
            used.add(letter)
        pieces = S.ground_areas(src, ops)
        if len(pieces) >= ALL_SEVEN_MIN_PIECES and used != set("ABCDEFG"):
            f.append("tile meshes used %s, not all seven (%d pieces)" % ("".join(sorted(used)), len(pieces)))
        # the moved targets back to their cells: the Assign offset is (-150, -150, 0) in the tile's frame
        off = tuple(AS._f32(x) for x in S.TILE_OFFSET)
        centres = []
        for v, _t in tiles:
            for i in range(len(v)):
                q = tuple(v.quat[i]) if v.quat else AS.quat_of(*v.rot[i])
                d = geo.quat_rotate(q, off)
                centres.append((v.loc[i][0] - d[0], v.loc[i][1] - d[1]))
        ground = _Index(pieces)
        excluded = _Index(src["undividable"] + src["small_park"] + src["reserved"])
        tower = _Index(src["tower"])
        walk = None
        if src["city"]:
            half = src["artery"] / 2.0 if src["artery"] is not None else S.EXPAND_DEFAULT_CM
            walk = _Index(A.expand(src["city"], half, ops))
        bad = {"outside the ground area": 0, "deep in an excluded area": 0, "in the landmark": 0,
               "outside the pedestrian area": 0}
        for c in centres:
            if not ground.near(c, EDGE_EPS_CM):
                bad["outside the ground area"] += 1
            for p in excluded.holders(c):
                if dist_to_ring(c, p.outer) > S.GROUND_EXPAND_CM + EDGE_EPS_CM:
                    bad["deep in an excluded area"] += 1
                    break
            if any(True for _ in tower.holders(c)):
                bad["in the landmark"] += 1
            if walk is not None and not walk.near(c, EDGE_EPS_CM):
                bad["outside the pedestrian area"] += 1
        for what, n in bad.items():
            if n:
                f.append("%d of %d tile centres %s" % (n, len(centres), what))
        # CONSISTENCY, not an invariant: the expected count is rebuilt with the stage's own fill.
        want = sum(len(G.fill_uniform(p.outer, p.z, S.TILE_EXTENT_CM)[0]) for p in pieces)
        if want != len(centres):
            f.append("tile sets hold %d tiles, the ground pieces fill %d" % (len(centres), want))

    # ---- sidewalk segments ----
    segs = [v for v in geo.values(outputs.get("SidewalkSegments", [])) if isinstance(v, geo.Spline)]
    if src["lots"] or src["city"] or src["tower"]:
        # Each segment's source, built independently of the stage's own chain where the brief names one:
        # the lot rings as read; the City grown by half the artery width; the landmark contracted 3 m.
        half = src["artery"] / 2.0 if src["artery"] is not None else S.EXPAND_DEFAULT_CM
        sources = [(lot.outer, True, S.LOT_CUT_DEG) for lot in src["lots"]]
        sources += [(g.outer, True, S.LOT_CUT_DEG) for g in A.expand(src["city"], half, ops)]
        sources += [(lm.outer, True, S.LANDMARK_CUT_DEG) for lm in A.contract(src["tower"], S.LANDMARK_SETBACK_CM, ops)]
        far = 0
        for s in segs:
            pts = [q[:2] for q in s.points]
            if len(pts) < 2:
                f.append("a sidewalk segment has %d points" % len(pts))
                continue
            mid = _midpoint(pts)
            hit = [cut for ring, closed, cut in sources if dist_to_ring(mid, ring, closed) <= SEGMENT_TOL_CM]
            if not hit:
                far += 1
                continue
            turns = _turns(pts)
            if turns and max(turns) > max(hit) + 1e-9:
                f.append("a sidewalk segment turns by %.2f deg, over its cut angle" % max(turns))
        if far:
            f.append("%d of %d sidewalk segments do not run along a lot, boundary or landmark edge" % (far, len(segs)))
        bound = S.boundary(src, ops) if src["city"] else []
        landmark = []
        for t in src["tower"]:
            landmark += A.in_frame(t, lambda p: A.contract([p], S.LANDMARK_SETBACK_CM, ops))
        # CONSISTENCY, not an invariant: the expected count is rebuilt with the stage's own functions.
        want = sum(len(S.segments_of(r, c, S.LOT_CUT_DEG)) for r, c, _z, _y in bound)
        want += sum(len(S.segments_of(lot.outer, True, S.LOT_CUT_DEG)) for lot in src["lots"])
        want += sum(len(S.segments_of(lm.outer, True, S.LANDMARK_CUT_DEG)) for lm in landmark)
        if want != len(segs):
            f.append("%d sidewalk segments, the sources cut into %d" % (len(segs), want))

    # ---- corners and railings ----
    corners = geo.values(outputs.get("CornerShapes", []))
    lots_in = sum(1 for c in corners if isinstance(c, geo.Polygon) and any(c.outer == l.outer for l in src["lots"]))
    if lots_in != len(src["lots"]):
        f.append("corner shapes hold %d of the %d lots" % (lots_in, len(src["lots"])))
    lots = _Index(src["lots"])
    for z in geo.values(outputs.get("RailingZones", [])):
        if not isinstance(z, geo.Polygon) or len(z.outer) < 3:
            f.append("a railing zone is not a polygon")
            continue
        cx = sum(p[0] for p in z.outer) / len(z.outer)
        cy = sum(p[1] for p in z.outer) / len(z.outer)
        if not all(lots.near(p, 1.0) for p in z.outer):
            f.append("a railing zone reaches outside the lots (centre %.0f, %.0f)" % (cx, cy))
        if src["lots"] and abs(z.z - (src["lots"][0].z + S.RAILING_LIFT_CM)) > 1e-9:
            f.append("a railing zone sits at z %.3f, not the lots' + %.0f" % (z.z, S.RAILING_LIFT_CM))
    return f


def _same(a, b):
    return [[geo.to_json(v), list(t)] for v, t in a] == [[geo.to_json(v), list(t)] for v, t in b]


def check_record(rec, ops, official=None):
    """The partial replay and the invariants on one recorded run (see the module docstring)."""
    from pypcg import stage_api
    f = []
    inputs = {}
    for pin, items in rec.get("inputs", {}).items():
        if pin == "MeshTerrain":
            continue
        inputs[pin] = [(geo.from_json(v), frozenset(t)) for v, t in items]
    inputs["MeshTerrain"] = [(_Flat(), frozenset())]
    params = {k: v for k, v in rec.get("params", {}).items()}
    again, _ctx = stage_api.execute(S, inputs, params, ops)
    recorded = rec.get("outputs", {})
    for pin in ("SidewalkSegments", "CornerShapes", "RailingZones"):
        mine = [[geo.to_json(v), list(t)] for v, t in again.get(pin, [])]
        if mine != [[v, list(t)] for v, t in recorded.get(pin, [])]:
            f.append("partial replay: %s differs from the record" % pin)
    sizes = [(v.get("n"), list(t)) for v, t in recorded.get("GroundTiles", [])]
    mine = [(len(v), list(t)) for v, t in again.get("GroundTiles", [])]
    if sizes != mine:
        f.append("partial replay: tile sets %s, recorded %s" % (mine, sizes))
    f += check(inputs, {k: v for k, v in params.items() if k != stage_api.SEED}, again, ops, official)
    return f
