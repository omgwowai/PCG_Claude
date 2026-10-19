"""Stage 17 -- CityEdge (PCG_5_1_CityEdge, 滨水设施).

Docks and warehouses on the city's waterfront: the final mesh terrain's points above the sea, their
2D convex hull, a share of the hull's vertices as dock sites facing along the hull, and one of five
pier / warehouse kits assigned to each through the `Assign_Assets` helper (`pypcg.geo.assets`). The
kept `Spawn_Assets` node spawns them. Replaces the official graph's ten computation nodes, from
`FilterDataByType_0` to `Subgraph_2 Assign_Assets`. See docs/pypcg/stages/s17.md.
"""
import math

from pypcg import geo
from pypcg.geo import Points
from pypcg.geo import assets as A
from pypcg.stage_api import Param

STAGE = 17
DOC = """CityEdge (滨水设施): the mesh terrain's points above SeaLevel, their 2D convex hull, a DockRatio
share of the hull's vertices (drawn with Python's own random numbers), each turned to face the next
hull vertex and assigned one of five pier / warehouse kits (Dock_A/B, Warehouse_A/B/C), placed 492.54 cm
inland. The kept Spawn_Assets node spawns the kits. Heights in cm."""
RANDOM = True
PARAMS = {
    "SeaLevel": Param(-72.639648, "Terrain points at or below this height (cm) are sea; the docks ring "
                                  "the land above it. The official AttributeFilter_0 threshold "
                                  "(Greater, on $Position.Z)", category="Docks"),
    "DockRatio": Param(0.5152000188827515, "Share of the land's convex hull vertices that get a dock "
                                           "(rounded up, as the official RandomChoice_0 does)",
                       category="Docks"),
}
INPUTS = {"MeshTerrain": "points"}
OUTPUTS = ("Docks",)

# `Subgraph_2 Assign Pier & Warehouse Assemblies`' own overrides.
ASSETS = ("/CitySamplePCG/PCG/DataAssets/Piers/Dock_A_PCG.Dock_A_PCG",
          "/CitySamplePCG/PCG/DataAssets/Piers/Dock_B_PCG.Dock_B_PCG",
          "/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_A_PCG.Warehouse_A_PCG",
          "/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_B_PCG.Warehouse_B_PCG",
          "/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_C_PCG.Warehouse_C_PCG")
POSITION_OFFSET = (0.0, -492.541261, 0.0)
ROTATION_OFFSET = (0.0, 0.0, 0.0)
ASSIGN_PARAMS = {"position_offset": POSITION_OFFSET, "rotation_offset": ROTATION_OFFSET}
TAG = "Docks"


def above(points, sea_level):
    """`AttributeFilter_0`: the points whose `$Position.Z` is GREATER than the threshold (the node's
    default operator), in input order. Measured 2026-10-19: 100 666 of 263 364, the same points in the
    same order as the official node."""
    return [p for p in points.loc if p[2] > sea_level]


def hull_ring(locs):
    """`FindConvexHull2D_0` -> `CreateSpline_0` (closed, linear) -> `GetSplineControlPoints_1`: the hull
    vertices in the engine's order (`geo.convex_hull`, counter-clockwise from the lowest X). A closed
    linear spline through them gives them back as its control points unchanged (measured: all 57
    locations bit for bit)."""
    return [locs[i] for i in geo.convex_hull(locs)]


def control_points(ring):
    """The control points of the closed linear spline through `ring`, as `GetSplineControlPoints`
    writes them, with `AttributeMathsOp_3/4`'s roll and pitch already zeroed: each at its vertex, its
    yaw toward the NEXT vertex (the spline's tangent there; the last one points back at the first),
    scale 1, box +-1, density and steepness 1, and the seed `ComputeSeedFromPosition` gives
    (`PCGHelpers.cpp:50`: `ComputeSeed(int(x), int(y), int(z))`). Measured against the official taps:
    the yaw to 8.5e-14 deg and all 57 seeds exactly."""
    pts = Points()
    quats = []
    n = len(ring)
    for k, p in enumerate(ring):
        q = ring[(k + 1) % n]
        yaw = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) if n > 1 else 0.0
        pts.add(p, rot=(0.0, yaw, 0.0), steepness=1.0,
                seed=A.compute_seed(int(p[0]), int(p[1]), int(p[2])))
        quats.append(A.quat_of(0.0, yaw, 0.0))
    pts.quat = quats
    return pts


def docks(points, params, rng):
    """The dock targets of one terrain point set: the hull's control points, a `DockRatio` share of
    them (`RandomChoice_0`, rounded UP like the engine's `CeilToInt`, chosen in hull order), roll and
    pitch already zero. Returns `(targets, ring)`."""
    ring = hull_ring(above(points, float(params["SeaLevel"])))
    ctrl = control_points(ring)
    keep = geo.choose(len(ctrl), float(params["DockRatio"]), rng, ceil=True)
    targets = ctrl.take(keep)
    targets.quat = [ctrl.quat[i] for i in keep]
    return targets, ring


def run(inputs, params, ctx):
    """`Docks`: the `Assign_Assets` output, item for item -- one point set per kit (its own points on
    each of its docks), then the docks themselves carrying the kit path. Every item goes to the kept
    `Spawn_Assets`, which spawns the kit points of the copies AND of the docks, as the official graph
    does (the official instance count is exactly twice the copies' meshed points)."""
    out = {"Docks": []}
    targets = None
    for data_index, (value, _tags) in enumerate(inputs.get("MeshTerrain", [])):
        if not isinstance(value, Points) or not len(value):
            continue
        t, ring = docks(value, params, ctx.rng)
        ctx.notes.append("terrain %d: %d points, hull %d vertices, %d docks"
                         % (data_index, len(value), len(ring), len(t)))
        # `Assign_Assets_CoreProcess`' `AttributeMathsOp_13`: `$Seed += dataIndex` before the merge.
        t.seed = [A._i32(s + data_index) for s in t.seed]
        if targets is None:
            targets = t
        else:
            targets.extend(t)                       # `Points.extend` carries both quaternion columns
    if targets is None or not len(targets):
        return out
    loader = getattr(ctx.ops, "assets", None)
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): nothing assigned")
        return out
    table = loader(list(ASSETS))
    picks = A.choose(len(targets), ASSETS, ctx.rng)
    for item in A.expand_items(targets, table, picks, dict(ASSIGN_PARAMS)):
        out["Docks"].append((item, [TAG]))
    return out
