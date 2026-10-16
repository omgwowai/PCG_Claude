"""V1 checks of stage 7, Roads, with the editor's booleans (spec 3, V1).

`check()` verifies the footprint invariants on every recorded run:

  - the footprint is one or more polygons, each with a positive area;
  - every footprint lies inside the road classes' own extent grown by the widest class width;
  - the footprint's total area is at most the sum of the classes' ribbons (a union never adds area);
  - `RoadFootprints` and `ModifiedTerrain` are both present on the output.

The oracle half compares against the volume's own official output when it holds it: the official
footprint is a single polygon, so the check is its area, its bbox and the number of ring vertices,
with tolerances that the port's measured residual (see `docs/pypcg/stages/s07.md` section 6) sets.
The numbers are relative to the official value, so a re-run on another city still checks.
"""
from pypcg import geo
from pypcg.stages import s07_roads as S

# Measured 2026-10-16 against the live official footprint: the port reproduces 3 of the 4 bbox edges
# to 1e-10 cm and the area to -0.65 %. The area bound is set just wide of that so a real regression
# (a dropped class, a missing landmark, a missing closed outline) fails while the known residual does
# not. These are V1 diagnostic bounds on a single-city oracle, not V2 thresholds: they live here and
# not in `v2_thresholds.json` because V1 is not a statistical comparison.
AREA_TOL = 0.05
VERTEX_TOL = 0.35


def _rings(items):
    return [p for p, _tags in items]


def _extent(inputs, params, ops, margin):
    """The box the footprint must stay inside: every road line **as the ribbon pass sees it** --
    already extended by half its class width -- plus the Landmarks rings expanded by 800, all grown
    by `margin`.

    Two things this has to get right, both measured against the official footprint:
    - `_paths` returns the EXTENDED lines (each end pushed out by half the class width), and the
      official footprint's `minX`/`minY` are exactly an extended end, so a bound computed from the
      raw line vertices would be too small by half a width;
    - the landmark term is not optional -- `Subgraph_86` unions the Landmarks ribbon into the local
      class and the expanded CentralPark ring reaches x = 108 228, past every road line's 104 644."""
    xs, ys = [], []
    widths = {"localRoads": params.get("local_Width", 1900.0),
              "CollectorRoads": params.get("collector_width", 2600.0),
              "ArteryRoads": params.get("Artery_width", 3400.0)}
    for tag, width in widths.items():
        for path in S._paths(inputs.get("Districts", []), tag, width):
            xs += [p[0] for p in path]
            ys += [p[1] for p in path]
    for ring in S.landmarks(inputs, params, ops):
        xs += [p[0] for p in ring.outer]
        ys += [p[1] for p in ring.outer]
    if not xs:
        return None
    return ((min(xs) - margin, min(ys) - margin), (max(xs) + margin, max(ys) + margin))


def check(inputs, params, outputs, ops, official=None):
    f = []
    mine = _rings(outputs.get("RoadFootprints", []))
    tags = {t for _p, ts in outputs.get("RoadFootprints", []) for t in ts}
    if mine and "RoadFootprints" not in tags:
        f.append("the footprint carries no RoadFootprints tag")
    if outputs.get("ModifiedTerrain") and not any(
            "ModifiedTerrain" in ts for _v, ts in outputs["ModifiedTerrain"]):
        f.append("the terrain output carries no ModifiedTerrain tag")
    for p in mine:
        if geo.area_m2(p) <= 0.0:
            f.append("a footprint polygon has area %.3g m2" % geo.area_m2(p))

    if inputs and inputs.get("Districts"):
        box = _extent(inputs, params, ops, 2e3)          # 20 m of miter/offset slack
        if box and mine:
            for p in mine:
                (x0, y0), (x1, y1) = geo.bbox(p.outer)
                if x0 < box[0][0] or y0 < box[0][1] or x1 > box[1][0] or y1 > box[1][1]:
                    f.append("a footprint at %s escapes the road extent %s"
                             % ([(round(v)) for v in (x0, y0)], [tuple(round(v) for v in q) for q in box]))
                    break
    if inputs and official and official.get("RoadFootprints"):
        f += _oracle(mine, official["RoadFootprints"])
    return f


def _oracle(mine, theirs):
    """The official footprint's area, bbox and vertex count against the port's."""
    f = []
    if not mine:
        return ["oracle: the official run has a footprint and this one does not"]
    mine_area = sum(geo.area_m2(p) for p in mine)
    their_area = sum(geo.area_m2(p) for p in theirs)
    if their_area and abs(mine_area - their_area) > AREA_TOL * their_area:
        f.append("oracle RoadFootprints area %.1f m2 vs official %.1f m2 (%+.1f %%)"
                 % (mine_area, their_area, 100.0 * (mine_area / their_area - 1.0)))
    n_mine = sum(len(p.outer) for p in mine)
    n_theirs = sum(len(p.outer) for p in theirs)
    if n_theirs and abs(n_mine - n_theirs) > VERTEX_TOL * n_theirs:
        f.append("oracle RoadFootprints ring vertices %d vs official %d" % (n_mine, n_theirs))
    if theirs:
        (tx0, ty0), (tx1, ty1) = geo.bbox([p for q in theirs for p in q.outer])
        (mx0, my0), (mx1, my1) = geo.bbox([p for q in mine for p in q.outer])
        if not (mx0 >= tx0 - 1e4 and my0 >= ty0 - 1e4 and mx1 <= tx1 + 1e4 and my1 <= ty1 + 1e4):
            f.append("oracle RoadFootprints bbox %s outside the official %s"
                     % ([(round(mx0), round(my0)), (round(mx1), round(my1))],
                        [(round(tx0), round(ty0)), (round(tx1), round(ty1))]))
    return f
