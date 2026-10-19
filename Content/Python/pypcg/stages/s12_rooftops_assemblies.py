"""Stage 12 -- Rooftops, second Python node: the WFC assemblies less the small ones (`s12_rooftops_assemblies`).

After the kept fitting-asset nodes (`SpawnAssets` false: each hands over its assemblies' mesh points, one point
data per area, every point carrying `Asset`, `Material`, `dataIndex`, `Asset Type Str` ...):

  DIFFERENCE  [Subgraph_12 Compose_Points_Difference "Subtract Small Assemblies From WFC Points"; inside it
              `Difference_0` (Mode Discrete, DensityFunction Binary, bDiffMetadata false) between the Primary
              input's point data (the WFC points, Subgraph_7) and the Secondary's (the small assemblies' points,
              Subgraph_2), then `ToPoint_0`]: each WFC point data on its own, against all the small points at once
              (`UPCGDifferenceData::AddDifference` per Secondary item, a union). A WFC point is dropped when any
              small point of density > 0 overlaps it with positive volume -- the small point's DENSITY box (its
              bounds x (2 - steepness); the fitting nodes' points carry steepness 0.5, so x 1.5) against the WFC
              point's plain bounds, both ways (`PCGPointHelpers::VolumeOverlap`; `geo.ground.difference_binary`) --
              and also when its own density is not above 0. A kept point is the source point as it was. With no
              small point at all, the WFC data pass through untouched. Empty results are dropped
              (`Primitives_PrepareOutputs`' `RemoveEmptyData`).
  OUT         -> the kept `Subgraph_13 Spawn All Rooftop Assemblies`, first of its inputs (`Branch_1`'s In order:
              this, Subgraph_11, Subgraph_3, Subgraph_2).

The points are written back with their own engine quaternions (`EXACT_ROTATIONS`), so a kept point reaches the
spawner bit for bit.
"""
from pypcg import geo
from pypcg.geo import ground as G

STAGE = 12
RECORD = "s12_assemblies"
DOC = """Rooftops, assemblies: the WFC rooftop assemblies' meshes less every one a small rooftop assembly overlaps."""
RANDOM = False
EXACT_ROTATIONS = True
PARAMS = {}
INPUTS = {"WfcPoints": "points", "SmallPoints": "points"}
OUTPUTS = ("Points",)


def rows(pts):
    """`(loc, quat, scale, bounds_min, bounds_max, density, steepness)` per point: the form
    `geo.ground.difference_binary` reads. The engine quaternion when `convert` gave one, else the rotator's."""
    from pypcg.geo import assets as AS
    quats = pts.quat if pts.quat and len(pts.quat) == len(pts) else [AS.quat_of(*r) for r in pts.rot]
    return [(pts.loc[i], quats[i], pts.scale[i], pts.bounds_min[i], pts.bounds_max[i], pts.density[i],
             pts.steepness[i]) for i in range(len(pts))]


def take(pts, idx):
    """The points at `idx`, every column and attribute, the engine quaternions kept."""
    out = pts.take(idx)
    if pts.quat and len(pts.quat) == len(pts):
        out.quat = [pts.quat[i] for i in idx]
    return out


def difference(wfc, small):
    """[Points] -- each WFC item less what the small items overlap, in order; empty results dropped. Every WFC
    item is tested against the same union, so they go through `difference_binary` in one call (the small points
    are indexed once) and are split back afterwards."""
    if not small:
        return [p for p in wfc if len(p)], 0
    diffs = [r for p in small for r in rows(p)]
    sources, owner = [], []
    for k, p in enumerate(wfc):
        sources += rows(p)
        owner += [(k, i) for i in range(len(p))]
    keep = {k: [] for k in range(len(wfc))}
    for j in G.difference_binary(sources, diffs, drop_empty_sources=True):
        k, i = owner[j]
        keep[k].append(i)
    out, removed = [], 0
    for k, p in enumerate(wfc):
        removed += len(p) - len(keep[k])
        if keep[k]:
            out.append(p if len(keep[k]) == len(p) else take(p, keep[k]))
    return out, removed


def run(inputs, params, ctx):
    wfc = [v for v, _t in inputs.get("WfcPoints", []) if isinstance(v, geo.Points)]
    small = [v for v, _t in inputs.get("SmallPoints", []) if isinstance(v, geo.Points)]
    out, removed = difference(wfc, small)
    ctx.notes.append("assemblies: %d WFC items, %d points; %d small items, %d points; %d WFC points removed, "
                     "%d kept in %d items" % (len(wfc), sum(len(p) for p in wfc), len(small),
                                              sum(len(p) for p in small), removed, sum(len(p) for p in out), len(out)))
    return {"Points": [(p, ["Type:Point", "Primitive:ComposePointsDifference"]) for p in out]}
