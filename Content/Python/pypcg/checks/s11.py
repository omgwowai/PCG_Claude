"""V1 checks of stage 11, Buildings (spec 3, V1).

The stage reads the final mesh terrain, so its run record cannot be replayed whole (trap 60). `check_record`
(which `pypcg_v1_editor.py` calls in place of `check`) does what a record allows, as stages 10 and 13 do:

  1. the PARTIAL REPLAY: the main node run again on the record's own non-surface inputs (the footprints
     with their engine vertices and frames, the texture heights, the HighRise splines with their frames),
     with its own seed and parameters, on a flat surface. The terrain moves the footprints in z (every vertex
     to the footprint's lowest terrain point) and, through the polygon frames the complex-shape split rebuilds,
     their XY in the last bits; so every stream's item count, kinds and heights must come out identical, XY
     within 1e-6 cm and the control-point yaws within 1e-6 deg;
  2. the task's invariants (`check`) on the record's own outputs.

`check(inputs, params, outputs, ops)` is the invariants alone (the brief's, as corrected in s11.md 5):

  - every texture height (the native write's output, the node's input) is inside its class's
    [MinHeight, MaxHeight] -- the heights the building nodes receive are not (the HighRise factor reaches 5,
    the complex shapes x 2 / x 1.3, Write_Noise up to 7000);
  - every footprint reaches exactly one building node: per class, Footprints + Complex = the input count;
  - HIGHRISE (`highrise`, per footprint, on the stage's own `footprints` -- the heights BEFORE the complex
    split, so it holds on the shipped ComplexBuildingShapes too): every footprint's height is >= its OWN
    texture height, and every footprint inside the HighRise zones is strictly taller (the factor is the mean
    of 1..5 remapped vertex distances, 1 only at the class's least deep vertex);
  - every medium complex height is in 2 x [2500, 7000], every large one 1.3 x its own > 3500;
  - each footprint sits flat (one z for all its vertices: `Transform_Level` Min);
  - SpawnMeshes is true (Partitioned is dropped, so the building nodes spawn their meshes)."""
from pypcg import geo
from pypcg.geo import ParamSet, Polygon, Spline
from pypcg.stages import s11_buildings as S

TOL = 1e-6
LEVEL_CM = 1e-6          # a footprint read back through a polygon frame carries ~1e-12 cm of z noise (s11.md 2.6)
XY_CM = 1e-6             # the replay's flat surface moves the frames' centroids, so recomputed vertices move in
YAW_DEG = 1e-6           # the last bits (s11.md 2.6); the heights and the item lists must be exact


class _Flat:
    """A flat surface: the partial replay needs the XY, the selections and the heights, not the z."""

    kind = "flat"

    def height(self, x, y):
        return 0.0


def _values(outputs, pin):
    return [v for v, _t in outputs.get(pin, [])]


def _heights(outputs, stream):
    return [v.values.get(S.HEIGHT) for v in _values(outputs, stream + "Heights") if isinstance(v, ParamSet)]


def _zs(v):
    if isinstance(v, Spline):
        return {p[2] for p in v.points}
    if isinstance(v, Polygon):
        return {v.z}
    return set()


def check(inputs, params, outputs, ops, official=None):
    f = []
    if inputs is None:
        return f
    for cls in S.CLASSES:
        lo, hi = params.get("MinHeight%sDistrict" % cls), params.get("MaxHeight%sDistrict" % cls)
        base = S.heights(inputs.get(cls + "Heights", []))
        n = len([v for v, _t in inputs.get(cls + "Lots", []) if isinstance(v, Polygon)])
        if lo is not None and hi is not None:
            out = [h for h in base if not (lo - TOL <= h <= hi + TOL)]
            if out:
                f.append("%s: %d texture heights outside [%g, %g] (e.g. %.3f)" % (cls, len(out), lo, hi, out[0]))
        got = len(_values(outputs, cls + "Footprints")) + len(_values(outputs, cls + "Complex"))
        if got != n:
            f.append("%s: %d footprints in, %d delivered to the building nodes" % (cls, n, got))
        for s in (cls + "Footprints", cls + "Complex"):
            if len(_values(outputs, s)) != len(_heights(outputs, s)):
                f.append("%s: %d footprints but %d heights" % (s, len(_values(outputs, s)), len(_heights(outputs, s))))
            flat = [v for v in _values(outputs, s) if _zs(v) and max(_zs(v)) - min(_zs(v)) > LEVEL_CM]
            if flat:
                f.append("%s: %d footprints are not level" % (s, len(flat)))
    if params.get("ComplexBuildingShapes"):
        lo, hi = S.NOISE
        bad = [h for h in _heights(outputs, "MediumComplex") if not (S.SCALE["Medium"] * lo - TOL <= h <= S.SCALE["Medium"] * hi + TOL)]
        if bad:
            f.append("MediumComplex: %d heights outside 2 x [%g, %g]" % (len(bad), lo, hi))
        bad = [h for h in _heights(outputs, "LargeComplex") if not h > S.SCALE["Large"] * S.TALL["Large"] - TOL]
        if bad:
            f.append("LargeComplex: %d heights not above 1.3 x %g" % (len(bad), S.TALL["Large"]))
    spawn = _values(outputs, "SpawnMeshes")
    if not spawn or not all(isinstance(v, ParamSet) and v.values.get("SpawnMeshes") is True for v in spawn):
        f.append("SpawnMeshes is not true")
    return f


def _same(a, b):
    """Two outputs alike apart from the terrain: same kind, vertex count and heights exactly, XY within
    `XY_CM`, control-point yaws within `YAW_DEG`."""
    if type(a) is not type(b):
        return False
    if isinstance(a, ParamSet):
        return a.values == b.values
    if isinstance(a, Spline):
        if len(a.points) != len(b.points) or a.closed != b.closed:
            return False
        if any(abs(p[0] - q[0]) > XY_CM or abs(p[1] - q[1]) > XY_CM for p, q in zip(a.points, b.points)):
            return False
        ra, rb = a.rotations or [], b.rotations or []
        return len(ra) == len(rb) and all(abs(((x[1] - y[1]) + 180.0) % 360.0 - 180.0) <= YAW_DEG for x, y in zip(ra, rb))
    if isinstance(a, Polygon):
        return len(a.outer) == len(b.outer) and len(a.holes) == len(b.holes) and all(
            abs(p[0] - q[0]) <= XY_CM and abs(p[1] - q[1]) <= XY_CM for p, q in zip(a.outer, b.outer))
    return True


def highrise(inputs, ops):
    """The HighRise invariant per footprint (module docstring), on `S.footprints` over the given inputs (the
    terrain only moves z, so a flat one does)."""
    f = []
    for cls in S.CLASSES:
        polys = [v for v, _t in inputs.get(cls + "Lots", []) if isinstance(v, Polygon)]
        base = S.heights(inputs.get(cls + "Heights", []))
        if not polys or len(base) != len(polys):
            continue
        fps, sel = S.footprints(polys, base, inputs.get("HighRise", []), ops, _Flat())
        low = [fp for fp in fps if not fp.height >= fp.base]
        flat = [fp for fp in fps if fp.selected and not fp.height > fp.base]
        if low:
            f.append("%s: %d footprints below their own texture height (e.g. #%d: %.6f < %.6f)"
                     % (cls, len(low), low[0].index, low[0].height, low[0].base))
        if flat:
            f.append("%s: %d HighRise footprints not taller than their texture height (e.g. #%d: %.6f vs %.6f)"
                     % (cls, len(flat), flat[0].index, flat[0].height, flat[0].base))
        if sorted(fp.index for fp in fps) != list(range(len(polys))) or len([fp for fp in fps if fp.selected]) != len(sel):
            f.append("%s: the footprints are not each input exactly once" % cls)
    return f


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
    params = dict(rec.get("params", {}))
    if not all(v.vertices for v, _t in inputs.get("SmallLots", []) + inputs.get("MediumLots", []) + inputs.get("LargeLots", [])):
        f.append("partial replay: the record's footprints carry no engine vertices (written before Task 20?)")
    again, _ctx = stage_api.execute(S, inputs, params, ops)
    recorded = {pin: [(geo.from_json(v), t) for v, t in items] for pin, items in rec.get("outputs", {}).items()}
    for pin in S.OUTPUTS:
        mine = [v for v, _t in again.get(pin, [])]
        theirs = [v for v, _t in recorded.get(pin, [])]
        bad = sum(1 for a, b in zip(mine, theirs) if not _same(a, b))
        if len(mine) != len(theirs) or bad:
            f.append("partial replay: %s differs from the record (%d vs %d items, %d unlike)" % (pin, len(mine), len(theirs), bad))
    outputs = {pin: [(v, frozenset(t)) for v, t in items] for pin, items in recorded.items()}
    rec_inputs = {k: v for k, v in inputs.items() if k != "MeshTerrain"}
    f += check(rec_inputs, {k: v for k, v in params.items() if k != stage_api.SEED}, outputs, ops, official)
    f += highrise(inputs, ops)
    return f
