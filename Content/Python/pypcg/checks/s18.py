"""V1 checks of stage 18, OuterForest (spec 3, V1).

The first node's record holds the terrain points (263 364, over `geo.MAX_RECORDED_POINTS`: a summary) and the
scattered point sets (three of the four over it on the demo level: summaries too), so the record cannot be replayed
whole (trap 60's situation) and V1 runs `check_record`, a PARTIAL REPLAY:

  - the footprint is the one the run noted (`footprint x0 y0 x1 y1 z`, exact reprs);
  - the City, park, highway and artery-width inputs are recorded in full, so the exclusion areas are rebuilt with
    the editor's booleans and the scatter is drawn again from the run's own seed (`Ctx`'s stream: the areas draw
    nothing, so the scatter's draws are the run's): every set must come out with the recorded size and bounds
    (and, where the record holds the points, the same points) -- the determinism evidence trap 60 asks for;
  - then the brief's invariants, as corrected in s18.md 5, on the replayed points: no point inside the grown city,
    the grown park or a highway polygon, every point inside the footprint and at its height with the primitive's
    +-10 cm box, and the scatter count equal to TreeDensity x available area within one point per boundary cell
    (`count_allowance`: the grid holds one point per cell, so only a cell the boundary crosses can go either way;
    on the demo level the official scatter is 117 points under the area's 308 902, its allowance 5 534).

The second node's record is empty on the demo level (the texture is missing, trap 66); its invariants
(`check_trees`) are run on the oracle (s18.md 7) and offline."""
import math
import random

from pypcg import geo
from pypcg.geo import areas as A
from pypcg.geo import ground as G
from pypcg.stages import s18_outer_forest as S
from pypcg.stages import s18_outer_forest_trees as T

COUNT_SLACK = 5                 # the scatter against TreeDensity x area: one point per boundary cell, plus this
Z_TOL_CM = 5.0                  # the brief's terrain tolerance


def footprint_of(notes):
    for n in notes or []:
        if n.startswith("footprint "):
            parts = n.split()[1:6]
            return tuple(float(x) for x in parts)
    return None


def _items(rec, side, pin):
    return rec.get(side, {}).get(pin, [])


def _values(rec, side, pin):
    out = []
    for v, tags in _items(rec, side, pin):
        try:
            out.append((geo.from_json(v), frozenset(tags)))
        except ValueError:
            out.append((v, frozenset(tags)))         # a summary (truncated points, a terrain placeholder)
    return out


def check_record(rec, ops, official=None):
    params = {k: v for k, v in rec["params"].items() if k != "Seed"}
    fp = footprint_of(rec.get("notes"))
    recorded = _items(rec, "outputs", "ForestPoints")
    if fp is None:
        if any("no terrain points" in n for n in rec.get("notes", [])):
            return [] if not recorded else ["no terrain points, but %d ForestPoints sets" % len(recorded)]
        return ["the run noted no footprint"]
    inputs = {pin: _values(rec, "inputs", pin) for pin in ("City", "CentralParkFootprint", "Highways", "ArteryWidth")}
    src = S.read(inputs)
    areas, city, park = S.forest_areas(fp, src, params, ops)
    rng = random.Random("%d:%d" % (int(rec["params"]["Seed"]), S.STAGE))      # stage_api.Ctx's stream
    sets = S.scatter(areas, float(params["TreeDensity"]), rng)
    f = []
    if len(sets) != len(recorded):
        return ["replay gave %d point sets, the run %d" % (len(sets), len(recorded))]
    for k, (s, (v, _tags)) in enumerate(zip(sets, recorded)):
        if v.get("n") != len(s):
            f.append("set %d: replay %d points, the run %d" % (k, len(s), v.get("n")))
            continue
        if v.get("truncated"):
            xs, ys, zs = zip(*s.loc)
            if v["bbox"] != [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]:
                f.append("set %d: replay bounds %s, the run %s" % (k, ((min(xs), min(ys)), (max(xs), max(ys))),
                                                                  v["bbox"]))
        elif geo.to_json(s) != v:
            f.append("set %d: replay differs from the run point for point" % k)
    f += check_scatter(fp, areas, city, park, src["highway"], sets, params)
    return f


def check_scatter(fp, areas, city, park, highways, sets, params):
    """The scatter invariants (s18.md 5): inside the footprint, outside every exclusion, at the footprint's height
    with a +-10 cm box, and TreeDensity x area within `count_allowance`."""
    f = []
    x0, y0, x1, y1, z = fp
    area_m2 = sum(A.area_cm2(a) for a in areas) / 1e4
    want = area_m2 * float(params["TreeDensity"])
    got = sum(len(s) for s in sets)
    allow = count_allowance(areas, float(params["TreeDensity"]))
    if abs(got - want) > allow:
        f.append("%d points scattered on %.1f m2; TreeDensity x area is %.1f (allowance %.0f)"
                 % (got, area_m2, want, allow))
    clips = [("grown city", c) for c in city] + [("grown park", p) for p in park] + [("highway", h) for h in highways]
    index = [(name, RingIndex(c)) for name, c in clips]
    bad = {}
    for s in sets:
        for j, p in enumerate(s.loc):
            if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
                bad["outside the footprint"] = bad.get("outside the footprint", 0) + 1
            if p[2] != z:
                bad["off the footprint's height"] = bad.get("off the footprint's height", 0) + 1
            if s.bounds_min[j] != (-S.POINT_EXTENT_CM,) * 3 or s.bounds_max[j] != (S.POINT_EXTENT_CM,) * 3:
                bad["box not +-10 cm"] = bad.get("box not +-10 cm", 0) + 1
            for name, ring in index:
                if ring.contains(p):
                    bad["inside the " + name] = bad.get("inside the " + name, 0) + 1
    f += ["%d scattered points %s" % (n, what) for what, n in sorted(bad.items())]
    return f


def count_allowance(areas, per_m2):
    """One point per grid cell the areas' boundaries cross (perimeter / cell), plus `COUNT_SLACK`."""
    if per_m2 <= 0:
        return COUNT_SLACK
    cell = math.sqrt(1e4 / per_m2)
    perimeter = sum(geo.path_length(list(r) + [r[0]]) for a in areas for r in [a.outer] + list(a.holes) if r)
    return perimeter / cell + COUNT_SLACK


class RingIndex:
    """`geo.contains` (inside the outer ring and in no hole: `geo.plane.inside`'s even-odd test) on a polygon
    with up to a thousand vertices, for hundreds of thousands of points: each ring's edges bucketed by 10 m rows
    (`geo.ground._row_edges`, the banded test `fill_random` uses), so a point tests only its row's edges."""
    ROW_CM = 1000.0

    def __init__(self, poly):
        ys = [q[1] for q in poly.outer]
        self.box = geo.bbox(poly.outer)
        self.j0, self.j1 = int(math.floor(min(ys) / self.ROW_CM)), int(math.floor(max(ys) / self.ROW_CM))
        self.outer = G._row_edges(poly.outer, self.ROW_CM, self.j0, self.j1)
        self.holes = [G._row_edges(h, self.ROW_CM, self.j0, self.j1) for h in poly.holes]

    def contains(self, p):
        (bx0, by0), (bx1, by1) = self.box
        if not (bx0 <= p[0] <= bx1 and by0 <= p[1] <= by1):
            return False
        j = int(math.floor(p[1] / self.ROW_CM))
        if not G._parity(p[0], p[1], self.outer.get(j, ())):
            return False
        return not any(G._parity(p[0], p[1], h.get(j, ())) for h in self.holes)


def scale_bounds(params, mega):
    """The tree scale bound of s18.md 5.4: [ScaleMin x 0.6 x offset x 0.8, ScaleMax x 1 x offset x 1.2], offset
    the call's `ScaleOffset` (0.7 for the Black Alder trees, 1 for the Megaplants)."""
    off = 1.0 if mega else T.T13.FOREST_SETTINGS["scale_offset"]["X"]
    r = T.T13.FOREST_SETTINGS["random_scale_range"]["X"]
    return (float(params["ScaleMin"]) * T.SCALE_FLOOR * off * (1.0 - r),
            float(params["ScaleMax"]) * 1.0 * off * (1.0 + r))


def scatter_keys(sets):
    """The (x, y) of every scattered point, for `check_trees`' "trees are scattered points" (s18.md 5.3)."""
    return {(p[0], p[1]) for s in sets for p in s.loc}


def check_trees(trees, params, surface=None, mega=False, slack=1e-6, scatter=None):
    """The tree invariants on one assigned point set (`Trees`' last item): every `Asset` one of the call's eight
    meshes, the scale uniform and within `scale_bounds`, pitch and roll within +-2 degrees, z above -450 and, with
    a surface, the terrain height under the tree within `Z_TOL_CM`; with `scatter` (`scatter_keys` of the first
    node's sets), every tree at a scattered point's (x, y) -- the projection and the assignment move no point in x, y,
    so the trees are a subset of the scatter (s18.md 5.3)."""
    f = []
    if scatter is not None:
        stray = sum(1 for p in trees.loc if (p[0], p[1]) not in scatter)
        if stray:
            f.append("%d trees stand where no point was scattered" % stray)
    paths = set(T.T13.MEGA if mega else T.T13.FOREST)
    assets = trees.attrs.get("Asset") or []
    if len(assets) != len(trees) or any(a not in paths for a in assets):
        f.append("trees carry assets outside the call's eight meshes")
    lo, hi = scale_bounds(params, mega)
    off = [i for i, s in enumerate(trees.scale) if not (lo - slack <= s[0] <= hi + slack)
           or abs(s[0] - s[1]) > slack or abs(s[0] - s[2]) > slack]
    if off:
        f.append("%d trees scaled outside [%.4f, %.4f] or not uniformly" % (len(off), lo, hi))
    tilt = [i for i, r in enumerate(trees.rot) if abs(r[0]) > 2.0 + slack or abs(r[2]) > 2.0 + slack]
    if tilt:
        f.append("%d trees tilted beyond +-2 degrees" % len(tilt))
    low = [i for i, p in enumerate(trees.loc) if not p[2] > T.CUT_Z_CM]
    if low:
        f.append("%d trees at or below %g cm" % (len(low), T.CUT_Z_CM))
    if surface is not None:
        far = 0
        for p in trees.loc:
            h = surface.height(p[0], p[1])
            if h is not None and abs(p[2] - h) > Z_TOL_CM:
                far += 1
        if far:
            f.append("%d trees more than %g cm off the terrain" % (far, Z_TOL_CM))
    return f


def check(inputs, params, outputs, ops, official=None):
    """Offline form (a replayable fixture): the scatter invariants from the inputs, and the trees' when given."""
    f = []
    if inputs is None:
        return f
    src = S.read(inputs)
    fp = S.footprint(src["terrain"])
    sets = [v for v in geo.values(outputs.get("ForestPoints", [])) if isinstance(v, geo.Points)]
    if fp is None:
        return ["no terrain, but %d ForestPoints sets" % len(sets)] if sets else []
    areas, city, park = S.forest_areas(fp, src, params, ops)
    return f + check_scatter(fp, areas, city, park, src["highway"], sets, params)

