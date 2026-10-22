"""V1 checks of stage 9, Lots, with the editor's booleans (spec 3, V1).

check() verifies, on every recorded run:
  - every building footprint lies inside a district of its own class, and outside the road
    footprint, the landmark, the central park, the small landmark park and the highway (overlap
    under 1 m2 each);
  - `UnderHighway` is non-empty exactly when the highway overlaps a buildable district class;
  - the KEPT share of the prepared lots is within 0.10 of `PlazaReservationRatio` (an item ratio:
    `Filter_RandomChoice` draws once per lot);
  - the area accounting closes: the prepared pieces (Lots less the undividable districts and the
    small park) equal reservedLots + unbuildableLots + the courtyards + UnderHighway + every
    footprint output (Small / Medium / Large, UnbuildableFootprints, LargeBuildingSkirt) + the grammar
    bands carved out of the large lots, within 1 % of the pieces;
  - no two building footprints overlap.

When the volume holds its official output (after V2's restore), it also runs the ORACLE: the
official `reservedLots` say which lots the official `Subgraph_3` reserved, so the stage is replayed
with that choice and must reproduce, to 0.05 m2 per item, everything that does not depend on a later
draw -- `Lots`, `reservedLots`, `unbuildableLots`, `Small Courtyards`, `Medium Courtyards`, items
under 0.01 m2 (Clipper's zero-area slivers) aside -- and,
in total area to 0.1 %, what the split draws only redistribute: `UnderHighway` and the footprint
total (every footprint output plus the skirt)."""
from pypcg import geo
from pypcg.geo import areas as A
from pypcg.stages import s09_lots as S

OVERLAP_M2 = 1.0
SHARE_TOL = 0.10
ACCOUNT_TOL = 0.01
ITEM_TOL_M2 = 0.05
TOTAL_TOL = 0.001
# Clipper leaves zero-area triangles where a 10 m grammar band's butt end meets a lot edge; which
# corners get one depends on the last bits of the band (the official run has 3, the replay 8, all
# under 0.001 m2, measured 2026-10-19). They carry no area, so the item comparisons skip them.
DEGENERATE_M2 = 0.01
EXACT = ("Lots", "reservedLots", "unbuildableLots", "Small Courtyards", "Medium Courtyards")
FOOTPRINT_TAGS = ("SmallDistrictsBldgFootprints", "MediumDistrictsBldgFootprints", "LargeDistrictsBldgFootprints",
                  "UnbuildableFootprints", "LargeBuildingSkirt")


def _by_tag(outputs):
    out = {}
    for pin, items in outputs.items():
        for v, tags in items:
            for t in tags:
                out.setdefault(t, []).append(v)
    return out


def _m2(polys):
    return sum(geo.area_m2(p) for p in polys if isinstance(p, geo.Polygon))


def _boxes_meet(a, b):
    return not (a[1][0] < b[0][0] or b[1][0] < a[0][0] or a[1][1] < b[0][1] or b[1][1] < a[0][1])


def _overlap_m2(p, clips, ops):
    box = geo.bbox(p.outer)
    clips = [c for c in clips if _boxes_meet(box, geo.bbox(c.outer))]
    if not clips:
        return 0.0
    return _m2(ops.intersection([p.outer] + list(p.holes), A.rings(clips)))


def pieces_of(inputs, ops):
    """`Subgraph_24`'s output: the lots `Subgraph_3` draws over (deterministic)."""
    city = S.areas_of(inputs.get("City", []))
    lots_1 = A.exclusion(A.exclusion(city, S.areas_of(inputs.get("RoadFootprints", [])), ops),
                         S.areas_of(inputs.get("CentralParkFootprint", [])) + S.areas_of(inputs.get("MainTower", [])), ops)
    return A.exclusion(A.exclusion(lots_1, S.areas_of(inputs.get("Districts", []), "UndividableDistricts"), ops),
                       S.areas_of(inputs.get("LandmarkPark", [])), ops)


_CACHE = {}


def _digest(obj):
    import hashlib
    import json
    h = hashlib.sha1()
    if isinstance(obj, dict):
        for k in sorted(obj):
            h.update(repr(k).encode())
            for v in obj[k]:
                v = v[0] if isinstance(v, tuple) else v
                h.update(json.dumps(geo.to_json(v), sort_keys=True).encode())
    return h.hexdigest()


def _key(inputs, official=None):
    """Runs of one V1 call share their inputs (the five V2 seeds read the same upstream), so the
    deterministic pieces and the oracle replay are computed once per input set. The key is a digest
    of the CONTENT (inputs and the official outputs), never an object id, and the cache keeps at most
    `_CACHE_MAX` entries."""
    return (_digest(inputs), _digest(official) if official else None)


_CACHE_MAX = 8


def _cached(k, fn):
    if k not in _CACHE:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[k] = fn()
    return _CACHE[k]


def check(inputs, params, outputs, ops, official=None):
    f = []
    by = _by_tag(outputs)
    fps = {c: by.get(S.TAGS[c + "Footprints"], []) for c in S.CLASSES}
    if inputs:
        districts = inputs.get("Districts", [])
        blockers = (S.areas_of(inputs.get("RoadFootprints", [])) + S.areas_of(inputs.get("MainTower", []))
                    + S.areas_of(inputs.get("CentralParkFootprint", [])) + S.areas_of(inputs.get("LandmarkPark", []))
                    + S.areas_of(inputs.get("Highway", [])))
        for c in S.CLASSES:
            own = S.areas_of(districts, c + "Districts")
            for p in fps[c]:
                outside = geo.area_m2(p) - _overlap_m2(p, own, ops)
                if outside > OVERLAP_M2:
                    f.append("a %s footprint of %.0f m2 lies %.1f m2 outside the %s districts"
                             % (c, geo.area_m2(p), outside, c))
                    break
            for p in fps[c]:
                o = _overlap_m2(p, blockers, ops)
                if o > OVERLAP_M2:
                    f.append("a %s footprint overlaps roads / landmarks / parks / highway by %.1f m2" % (c, o))
                    break
        highway = S.areas_of(inputs.get("Highway", []))
        classes = [p for c in S.CLASSES for p in S.areas_of(districts, c + "Districts")]
        crosses = bool(highway) and _m2(ops.intersection(A.rings(classes), A.rings(highway))) > OVERLAP_M2 \
            if classes else False
        if crosses != bool(by.get("UnderHighway")):
            f.append("UnderHighway has %d items but the highway %s the districts"
                     % (len(by.get("UnderHighway", [])), "crosses" if crosses else "does not cross"))
        pieces = _cached(("pieces",) + _key(inputs), lambda: pieces_of(inputs, ops))
        if pieces:
            kept = 1.0 - len(by.get("reservedLots", [])) / float(len(pieces))
            if len(pieces) >= 20 and abs(kept - params["PlazaReservationRatio"]) > SHARE_TOL:
                f.append("kept share %.3f of %d lots vs PlazaReservationRatio %.3f"
                         % (kept, len(pieces), params["PlazaReservationRatio"]))
            whole = _m2(pieces)
            bands = _m2(A.intersection(S.grammar_bands([s.points for s in by.get("GridSplines", [])], ops),
                                       [p for p in pieces], ops)) if by.get("GridSplines") else 0.0
            parts = sum(_m2(by.get(t, [])) for t in ("reservedLots", "unbuildableLots", "Small Courtyards",
                                                     "Medium Courtyards", "UnderHighway") + FOOTPRINT_TAGS)
            gap = whole - parts - bands
            if abs(gap) > ACCOUNT_TOL * whole:
                f.append("area accounting: pieces %.0f m2, outputs %.0f m2 + grammar bands %.0f m2 (gap %+.0f m2)"
                         % (whole, parts, bands, gap))
    built = [p for c in S.CLASSES for p in fps[c]]
    boxes = [geo.bbox(p.outer) for p in built]
    for i in range(len(built)):
        for j in range(i + 1, len(built)):
            (a0, a1), (b0, b1) = boxes[i], boxes[j]
            if a1[0] < b0[0] or b1[0] < a0[0] or a1[1] < b0[1] or b1[1] < a0[1]:
                continue
            o = _m2(ops.intersection([built[i].outer], [built[j].outer]))
            if o > OVERLAP_M2:
                f.append("two building footprints overlap by %.1f m2" % o)
                return f
    if inputs and official and official.get("reservedLots") is not None and official.get("Lots"):
        k = ("oracle",) + _key(inputs, official) + (tuple(sorted(params.items())),)
        f += _cached(k, lambda: oracle(inputs, params, ops, official))
    return f


class OfficialPlaza(S.Draws):
    """The official `Subgraph_3` outcome: a lot is reserved when an official `reservedLots` item
    has its area (0.05 m2) and its centroid (1 m). Every other draw is the stage's own."""

    def __init__(self, rng, reserved):
        super().__init__(rng)
        self.reserved = [(geo.area_m2(p), _centroid(p)) for p in reserved]

    def keep(self, step, items, ratio):
        if step != "plaza":
            return super().keep(step, items, ratio)
        out = []
        for p in items:
            a, c = geo.area_m2(p), _centroid(p)
            out.append(not any(abs(a - b) <= ITEM_TOL_M2 and abs(c[0] - d[0]) < 100 and abs(c[1] - d[1]) < 100
                               for b, d in self.reserved))
        return out


def _centroid(p):
    xs, ys = [q[0] for q in p.outer], [q[1] for q in p.outer]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def replay(inputs, params, ops, official, seed=42):
    import random
    return S.tagged(S.lots(inputs, params, ops, OfficialPlaza(random.Random(seed), official.get("reservedLots", []))))


def oracle(inputs, params, ops, official):
    f = []
    by = _by_tag(replay(inputs, params, ops, official))
    for t in EXACT:
        mine = sorted(a for a in (geo.area_m2(p) for p in by.get(t, [])) if a >= DEGENERATE_M2)
        theirs = sorted(a for a in (geo.area_m2(p) for p in official.get(t, [])) if a >= DEGENERATE_M2)
        if len(mine) != len(theirs) or any(abs(a - b) > ITEM_TOL_M2 for a, b in zip(mine, theirs)):
            f.append("oracle %s: %d items %.1f m2 vs official %d items %.1f m2"
                     % (t, len(mine), sum(mine), len(theirs), sum(theirs)))
    for label, tags in (("UnderHighway", ("UnderHighway",)), ("footprint total", FOOTPRINT_TAGS)):
        mine = sum(_m2(by.get(t, [])) for t in tags)
        theirs = sum(_m2(official.get(t, [])) for t in tags)
        if abs(mine - theirs) > TOTAL_TOL * max(theirs, 1.0):
            f.append("oracle %s: %.1f m2 vs official %.1f m2 (%+.3f %%)"
                     % (label, mine, theirs, 100.0 * (mine - theirs) / max(theirs, 1.0)))
    return f
