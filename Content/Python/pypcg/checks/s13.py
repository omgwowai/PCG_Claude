"""V1 checks of stage 13, LeftOverLots (spec 3, V1).

The stage reads the final mesh terrain, so its run record cannot be replayed whole (trap 60). `check_record`
(which `pypcg_v1_editor.py` calls in place of `check`) does what a record allows, as stage 10's does:

  1. the PARTIAL REPLAY: the stage run again on the record's own non-surface inputs, with its own seed, on a
     flat surface. Everything the terrain does not touch must come out identical, field for field: the
     published plaza lots and the five fitting-node area sets; and every tile set and tree set's size and
     tag (the draws are the seeded part; the terrain only moves points in z and tilts them);
  2. the task's invariants (`check`) on the record's own outputs and that replay.

`check(inputs, params, outputs, ops)` is the invariants alone:

  - every published plaza lot IS one of the reserved lots (the official graph publishes the plaza-side lots
    its second draw did not keep, untouched -- `Reroute_4`), and none is also fitted with plazas;
  - every setback area (reserved plaza lots, under-highway lots, both courtyard classes) lies inside its
    source and is smaller (contracted, never grown), 30 cm above it;
  - the skirt areas are the stage-9 `LargeBuildingSkirt` items lifted 30 cm -- the node TITLED "Only
    unbuildable lots" (`Subgraph_36`) filters `LargeBuildingSkirt` -- and none is an unbuildable lot;
  - the plaza / tree split is on items: on 20 lots or more the plaza share is within 0.10 of
    `Ratio_Plaza_vs_Trees` (one draw per lot);
  - tree points lie on the surface within 5 cm (on the replay's flat surface; the real terrain fit is the
    projector `geo.ground.project_tile`, measured point for point against the official one, s13.md 6);
  - every ground tile set carries one plaza tile mesh.

Two clauses are CONSISTENCY checks, not invariants: the tile and tree counts against the stage's own
functions on the replay. The algorithm is measured against the official graph instead
(`Tools/pypcg/data/s13_official_measurements.json`)."""
from pypcg import geo
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.stages import s13_leftover_lots as S

SHARE_TOL = 0.10
SHARE_MIN_ITEMS = 20
ON_SURFACE_CM = 5.0
INSIDE_TOL_CM = 1.0
SETBACK_PINS = {"ReservedPlazaAreas": None, "UnderHighwayAreas": "under", "SmallCourtyardAreas": "small_yards",
                "MediumCourtyardAreas": "medium_yards"}


class _Flat:
    """A flat surface: the partial replay needs the XY and the draws, not the heights."""

    kind = "flat"

    def height(self, x, y):
        return 0.0


def _same_poly(a, b):
    return a.outer == b.outer and a.holes == b.holes and a.z == b.z


def _inside(p, src):
    """Every vertex of `p` within `INSIDE_TOL_CM` of the inside of `src` (its outer ring)."""
    from pypcg.checks.s10 import dist_to_ring
    for q in p.outer:
        if not geo.inside(q, src.outer) and dist_to_ring(q, src.outer) > INSIDE_TOL_CM:
            return False
    return True


def _values(outputs, pin):
    return [v for v, _t in outputs.get(pin, [])]


def check(inputs, params, outputs, ops, official=None):
    f = []
    if inputs is None:
        return f
    src = S.read(inputs)
    reserved = src["reserved"]
    published = _values(outputs, "PlazaLots")
    for p in published:
        if not any(_same_poly(p, r) for r in reserved):
            f.append("a published plaza lot (%.1f m2) is not one of the reserved lots" % geo.area_m2(p))
            break
    fitted = _values(outputs, "ReservedPlazaAreas")
    # ---- the setbacks: inside a source, smaller, 30 cm up ----
    kept = [r for r in reserved if not any(_same_poly(r, p) for p in published)]
    for pin, key in SETBACK_PINS.items():
        sources = kept if key is None else src[key]
        for a in _values(outputs, pin):
            own = [s for s in sources if _inside(a, s)]
            if not own:
                f.append("a %s area (%.1f m2) lies outside every source" % (pin, geo.area_m2(a)))
                break
            if not any(geo.area_m2(a) < geo.area_m2(s) for s in own):
                f.append("a %s area (%.1f m2) is not smaller than its source" % (pin, geo.area_m2(a)))
                break
            if abs(a.z - (own[0].z + S.PLAZA_LIFT_CM)) > 1e-9:
                f.append("a %s area sits at z %.3f, not its source's + %.0f" % (pin, a.z, S.PLAZA_LIFT_CM))
                break
    for a in fitted:
        if any(_inside(a, p) for p in published):
            f.append("a published plaza lot is also fitted with plazas")
            break
    # ---- the skirt: the stage-9 LargeBuildingSkirt items, not the unbuildable lots ----
    skirt = _values(outputs, "SkirtAreas")
    if len(skirt) != len(src["skirt"]) or any(
            a.outer != s.outer or abs(a.z - (s.z + S.PLAZA_LIFT_CM)) > 1e-9 for a, s in zip(skirt, src["skirt"])):
        f.append("the skirt areas are not the %d LargeBuildingSkirt items lifted %.0f cm"
                 % (len(src["skirt"]), S.PLAZA_LIFT_CM))
    if any(a.outer == u.outer for a in skirt for u in src["unbuildable"]):
        f.append("an unbuildable lot reached the skirt plazas")
    # ---- the split: on items, the plaza share near the ratio ----
    n = len(reserved)
    if n >= SHARE_MIN_ITEMS:
        tree_side = n - len(published) - len([r for r in kept if any(_inside(a, r) for a in fitted)])
        share = 1.0 - tree_side / float(n)
        if abs(share - params["Ratio_Plaza_vs_Trees"]) > SHARE_TOL:
            f.append("plaza share %.3f of %d lots vs Ratio_Plaza_vs_Trees %.3f" % (share, n, params["Ratio_Plaza_vs_Trees"]))
    # ---- tiles and trees ----
    for pts, tags in outputs.get("GroundTiles", []):
        names = [t for t in tags if t.startswith("SM_Plaza_Square_")]
        assets = set(pts.attrs.get(AS.ASSET_ATTR) or [])
        if len(names) != 1 or assets != {S._MESH % (names[0][-1], names[0][-1])}:
            f.append("a tile set carries %s / %s, not one plaza mesh" % (names, sorted(assets)))
    surface = next((v for v, _t in inputs.get("MeshTerrain", []) if hasattr(v, "height")), None)
    if surface is not None:
        off = 0
        total = 0
        for pts, _t in outputs.get("TreePoints", []):
            if not isinstance(pts, geo.Points):
                continue
            for q in pts.loc:
                total += 1
                h = surface.height(q[0], q[1])
                if h is not None and abs(q[2] - h) > ON_SURFACE_CM:
                    off += 1
        if off:
            f.append("%d of %d tree points are more than %.0f cm off the surface" % (off, total, ON_SURFACE_CM))
    return f


def _json(items):
    return [[geo.to_json(v), list(t)] for v, t in items]


def check_record(rec, ops, official=None):
    """The partial replay and the invariants on one recorded run (see the module docstring)."""
    from pypcg import stage_api
    f = []
    inputs = {}
    skipped = 0
    for pin, items in rec.get("inputs", {}).items():
        if pin == "MeshTerrain":
            continue
        vals = []
        for v, t in items:
            try:
                vals.append((geo.from_json(v), frozenset(t)))
            except ValueError:
                # a surface on another pin (the Roads read carries stage 7's modified terrain): the stage
                # reads only that pin's areas, so the surface can go
                skipped += 1
        inputs[pin] = vals
    inputs["MeshTerrain"] = [(_Flat(), frozenset())]
    params = dict(rec.get("params", {}))
    again, _ctx = stage_api.execute(S, inputs, params, ops)
    recorded = rec.get("outputs", {})
    for pin in ("PlazaLots", "ReservedPlazaAreas", "UnderHighwayAreas", "SmallCourtyardAreas",
                "MediumCourtyardAreas", "SkirtAreas"):
        if _json(again.get(pin, [])) != [[v, list(t)] for v, t in recorded.get(pin, [])]:
            f.append("partial replay: %s differs from the record" % pin)
    for pin in ("GroundTiles", "TreePoints"):
        mine = [(len(v), list(t)) for v, t in again.get(pin, [])]
        theirs = [(v.get("n"), list(t)) for v, t in recorded.get(pin, [])]
        if mine != theirs:
            f.append("partial replay: %s sets %s, recorded %s" % (pin, mine[:6], theirs[:6]))
    rec_inputs = dict(inputs)
    outputs = {pin: [(geo.from_json(v), frozenset(t)) for v, t in items] for pin, items in recorded.items()
               if all(not v.get("truncated") for v, _ in items)}
    rec_inputs.pop("MeshTerrain")
    f += check(rec_inputs, {k: v for k, v in params.items() if k != stage_api.SEED}, outputs, ops, official)
    f += ["replay: %s" % x for x in check(inputs, {k: v for k, v in params.items() if k != stage_api.SEED},
                                          again, ops, official)]
    return f
