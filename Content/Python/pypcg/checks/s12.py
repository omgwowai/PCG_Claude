"""V1 checks of stage 12, Rooftops (spec 3, V1).

The main node's input is the stage-11 rooftops alone -- closed splines, recordable -- so V1 REPLAYS each run record
whole (`pypcg_v1_editor.py`: field for field) and then calls `check`. The second node, `s12_rooftops_assemblies`,
reads the fitting nodes' points; its record (`Saved/PyPCG/runs/s12_assemblies.json`) is checked here too when it is
on disk (`check_assemblies`), since V2 copies only the main one.

`check(inputs, params, outputs, ops, official)` -- the task's invariants on the record's outputs, each against this
module's OWN reading of the rooftops (`_roof`: the outline's area and z straight from the control points, not
`geo.frames`), so a wrong polygon read in the stage cannot hide here:

  - empty inputs -> every output empty;
  - every placement area lies inside a rooftop: its vertices on or inside the rooftop outline it came from (within
    `INSIDE_TOL_CM`), at that rooftop's z, or 8 / 20 cm under it for the two lowered sets;
  - the WFC, skyscraper and vent sets take disjoint rooftops, and every rooftop reaches a fitting node: all of them
    the small-assembly node but the medium <= 800 m2, which go to the vents;
  - the 70 m split is the AVERAGE z over the rooftop's vertices: the skyscraper set is exactly the large rooftops over
    500 m2 whose average z is above 7000 cm (on flat rooftops average = max, so the clause also pins the threshold);
  - the class and size split: by the exact class tags, and areas 300 / 800 / 500 m2 (Greater), from the shoelace area
    of the control points (within `AREA_TOL_CM2` of the threshold the clause abstains).
"""
import json
import math
import os

from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.stages import s12_rooftops as S

INSIDE_TOL_CM = 0.01
Z_TOL_CM = 1e-6
AREA_TOL_CM2 = 1.0
SIZE_M2 = {"SmallRooftops": 300.0, "MediumRooftops": 800.0, "LargeRooftops": 500.0}   # this module's own copy
SKYSCRAPER_CM = 7000.0
LOWER_CM = {"SmallAssemblyAreas": 8.0, "SkyscraperAreas": 20.0, "WfcAreas": 0.0, "VentAreas": 0.0}


def _roof(spline):
    """(xy ring, area cm2, average z) straight from the control points."""
    ring = [(p[0], p[1]) for p in spline.points]
    a = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % len(ring)]
        a += x0 * y1 - x1 * y0
    zs = [p[2] for p in spline.points]
    return ring, abs(a) * 0.5, sum(zs) / len(zs)


def _dist_to_ring(p, ring):
    best = float("inf")
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def _area_points(v):
    if isinstance(v, Polygon):
        zs = v.zs if v.zs is not None else [v.z] * len(v.outer)
        return [(x, y, z) for (x, y), z in zip(v.outer, zs)]
    return [tuple(p) for p in v.points]


def _owner(v, roofs, lower):
    """The index of the rooftop an output area came from: the one whose outline holds every vertex and whose z, less
    the set's offset, is the area's (a building's stacked rooftops can share XY)."""
    pts = _area_points(v)
    for k, (ring, _a, z) in enumerate(roofs):
        want = z - lower
        if abs(pts[0][2] - want) > Z_TOL_CM + 1e-9 * abs(want):
            continue
        if all(geo.inside(p[:2], ring) or _dist_to_ring(p[:2], ring) <= INSIDE_TOL_CM for p in pts):
            return k
    return None


def check(inputs, params, outputs, ops, official=None):
    fails = []
    if inputs is None:
        return ["no recordable inputs: stage 12's main node reads splines only, so a record always has them"]
    items = [(v, t) for v, t in inputs.get("Rooftops", []) if isinstance(v, Spline) and v.closed]
    if not items:
        busy = [pin for pin in S.OUTPUTS if outputs.get(pin)]
        return ["no rooftops but outputs on %s" % busy] if busy else []
    roofs = [_roof(v) for v, _t in items]
    classes = [next((c for c in SIZE_M2 if c in t), None) for _v, t in items]

    # every area inside its rooftop, at its z (less the offset)
    used = {pin: [] for pin in S.OUTPUTS}
    for pin in S.OUTPUTS:
        for v, _t in outputs.get(pin, []):
            k = _owner(v, roofs, LOWER_CM[pin])
            if k is None:
                fails.append("%s: an area inside no rooftop at that rooftop's z less %g cm (first vertex %s)"
                             % (pin, LOWER_CM[pin], _area_points(v)[:1]))
                continue
            used[pin].append(k)
            want = roofs[k][2] - LOWER_CM[pin]
            bad = [p[2] for p in _area_points(v) if abs(p[2] - want) > Z_TOL_CM + 1e-9 * abs(want)]
            if bad:
                fails.append("%s: rooftop %d's area at z %r, want %r" % (pin, k, bad[0], want))

    # the WFC / skyscraper / vent sets are disjoint, and every rooftop is placed
    sets = {pin: set(ks) for pin, ks in used.items()}
    for a, b in (("WfcAreas", "SkyscraperAreas"), ("WfcAreas", "VentAreas"), ("SkyscraperAreas", "VentAreas")):
        both = sets[a] & sets[b]
        if both:
            fails.append("%d rooftops in both %s and %s (first %d)" % (len(both), a, b, min(both)))
    for pin, ks in used.items():
        if len(ks) != len(set(ks)):
            fails.append("%s holds a rooftop twice" % pin)

    # the class / size / height split, from this module's own areas
    def expect(k):
        c, (_ring, area, z) = classes[k], roofs[k]
        if c is None:
            return None
        limit = SIZE_M2[c] * 1e4
        if abs(area - limit) <= AREA_TOL_CM2:
            return None                                             # at the threshold: abstain
        big = area > limit
        if c == "SmallRooftops":
            return {"SmallAssemblyAreas", "WfcAreas" if big else "VentAreas"}
        if c == "MediumRooftops":
            return {"SmallAssemblyAreas"} if big else {"VentAreas"}
        if not big:
            return {"SmallAssemblyAreas", "WfcAreas"}
        return {"SmallAssemblyAreas", "SkyscraperAreas" if z > SKYSCRAPER_CM else "WfcAreas"}
    for k in range(len(items)):
        want = expect(k)
        got = {pin for pin, ks in sets.items() if k in ks}
        if want is not None and got != want:
            fails.append("rooftop %d (%s, %.0f m2, z %.1f): placed by %s, want %s"
                         % (k, classes[k], roofs[k][1] / 1e4, roofs[k][2], sorted(got), sorted(want)))
    return fails[:40]


def check_record(rec, ops, official=None):
    """V1's entry (it replays the main node's record first): `check` on the record, then `check_assemblies` on the
    second node's own record when it carries the same seed (V2 copies only the main one; the assemblies record on
    disk is the last slim run's, `Saved/PyPCG/runs/s12_assemblies.json` -- seed 42, the last V2 seed -- so with five
    main records it is checked once, with the seed-42 one; no draw anywhere in the stage, so it stands for all)."""
    from pypcg import stage_api
    inputs = {pin: [(geo.from_json(v), frozenset(t)) for v, t in items] for pin, items in rec["inputs"].items()}
    outputs = {pin: [(geo.from_json(v), t) for v, t in items] for pin, items in rec["outputs"].items()}
    fails = check(inputs, {}, outputs, ops, official)
    path = os.path.join(stage_api.RUNS_DIR, "s12_assemblies.json")
    if not os.path.exists(path):
        return fails + ["no assemblies record (%s): the difference was not checked" % path]
    with open(path, encoding="utf-8") as fh:
        seed = (json.load(fh).get("params") or {}).get(stage_api.SEED)
    if seed == rec["params"].get(stage_api.SEED):
        fails += check_assemblies(path)
    return fails[:40]


def check_assemblies(path=None):
    """The second node's last run, when its record is on disk: every kept WFC point is a source point unchanged, in
    order; no kept point is overlapped by a small-assembly point; every dropped one is (the engine's
    `VolumeOverlap`, tested pair by pair without the broad phase the stage uses)."""
    from pypcg.geo import ground as G
    from pypcg.stage_api import RUNS_DIR
    from pypcg.stages import s12_rooftops_assemblies as A
    path = path or os.path.join(RUNS_DIR, "s12_assemblies.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    try:
        wfc = [geo.from_json(v) for v, _t in rec["inputs"].get("WfcPoints", [])]
        small = [geo.from_json(v) for v, _t in rec["inputs"].get("SmallPoints", [])]
        out = [geo.from_json(v) for v, _t in rec["outputs"].get("Points", [])]
    except ValueError:
        return []                                                     # a truncated (summary-only) record
    fails = []
    diffs = [r for p in small for r in A.rows(p)]
    if not diffs:
        return [] if sum(len(p) for p in out) == sum(len(p) for p in wfc) else ["no small points, yet points dropped"]
    ready = []
    for d in diffs:
        if d[5] > 0:
            k = G.density_scale(d[6])
            reach = max(abs(v) for v in tuple(d[3]) + tuple(d[4])) * k * max(abs(s) for s in d[2]) * 1.7320508075688772
            ready.append((d, reach))
    cell = 1000.0
    grid = {}
    for d, reach in ready:
        grid.setdefault((math.floor(d[0][0] / cell), math.floor(d[0][1] / cell)), []).append((d, reach))
    top = max((reach for _d, reach in ready), default=0.0)

    def overlapped(r):
        reach_s = max(abs(v) for v in tuple(r[3]) + tuple(r[4])) * max(abs(s) for s in r[2]) * 1.7320508075688772
        span = int(math.ceil((top + reach_s) / cell))
        cx, cy = math.floor(r[0][0] / cell), math.floor(r[0][1] / cell)
        for gx in range(cx - span, cx + span + 1):
            for gy in range(cy - span, cy + span + 1):
                for d, reach in grid.get((gx, gy), ()):
                    if math.dist(r[0], d[0]) <= reach + reach_s and G.volume_overlap(d[:5], r[:5], d[6]) > 0:
                        return True
        return False

    j = 0
    for p in wfc:
        kept = out[j] if j < len(out) else None
        rows = A.rows(p)
        krows = A.rows(kept) if kept is not None else []
        ptr = 0                                           # the kept points are a subsequence of the source's, in order
        n_kept = 0
        for i, r in enumerate(rows):
            hit = overlapped(r)
            same = ptr < len(krows) and krows[ptr] == r and all(
                kept.attrs.get(a, [None] * len(kept))[ptr] == col[i] for a, col in p.attrs.items())
            if same:
                ptr += 1
                n_kept += 1
                if hit:
                    fails.append("a kept WFC point at %s is overlapped by a small assembly" % (tuple(round(c, 1) for c in r[0]),))
            elif not hit and r[5] > 0:
                fails.append("a dropped WFC point at %s overlaps no small assembly" % (tuple(round(c, 1) for c in r[0]),))
        if n_kept:
            if kept is None or len(kept) != n_kept:
                fails.append("WFC item: %d points kept, the output item holds %s" % (n_kept, len(kept) if kept else None))
            j += 1
        if len(fails) > 20:
            break
    if j != len(out):
        fails.append("%d output items for %d non-empty results" % (len(out), j))
    return fails
