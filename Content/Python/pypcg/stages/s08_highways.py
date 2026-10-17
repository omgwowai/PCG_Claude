"""Stage 8 -- Highways (PCG_3_1_3_Highways, 高速).

Two highway spline actors become one footprint each: the splines are flattened to Z 0, resampled at
80 m, projected onto the final mesh terrain, clamped and rebuilt level, and each one is outlined into
an `Assign_ShapeGrammarDefinition` footprint (`SGD_ElevatedHighway_oneWay`) of `Highway_Width` wide,
grown by 15 m and tagged `Highway`.

The official graph is 34 nodes carrying 23 "python" ones, but that count treats each primitive as a
single node. Their real sizes, read out of their own dumps (2026-10-17): `Transform_Resample` 15 +
`Transform_Resample_CoreProcess` 15, `Transform_Project` 21 + `Transform_Project_CoreProcess` 129,
`Transform_Areas_Expand` 12 + its CoreProcess 8, `Filter_Tags` 12 + `Filter_Tags_FilterInputTags` 11,
`Assign_ShapeGrammarDefinition` 14 + its CoreProcess 48 + innerLoop 29 + PrepareOutputs 11. The real
surface is about 330 nodes, not 23; stage 7 found the same factor.

Reading the graph top to bottom:

  Subgraph_7 (the two HighwaySpline actors) -> AttributeMathsOp_0 ($Position.Z = 0)
    -> Subgraph_9 Transform_Resample (Distance 8000, SamplingMode Distance)
    -> Subgraph_8 Transform_Project (positions onto Subgraph_3's Final Mesh Terrain)
    -> GetSplineControlPoints_0 -> AttributeMathsOp_1 (Clamp $Position.Z to [-500, 1e9])
    -> CreateSpline_0 (linear) -> AttributeMathsOp_2/3 ($Rotation.Roll = 0, $Rotation.Pitch = 0)
    -> Assign_HighwayShapeGrammar (SGD_ElevatedHighway_oneWay, Size = Highway_Width,
       SpawnAssets false) -> Footprints
    -> Subgraph_0 Transform_Areas_Expand (Expand 1500) -> AddTag_Highway -> the `Highway` output.

  Assign_HighwayShapeGrammar's Points output -> AttributeCast_1 (Asset -> AssetString)
    -> FilterDataByType_2 -> AttributeFilter_1 (AssetString contains "Round", the pillars)
    -> FilterDataByType_5 -> Projection_0 (onto MakeConcrete_1 of Subgraph_1's RoadFootprints)
    -> FilterDataByType_3 -> AttributeFilter_2 ($Density == 1) -> Branch_0 -> Subgraph_4
       Spawn Highway Support Assets.

What this module computes is the READ SIDE of the grammar node -- steps 1 to 5 below, everything
`AttributeMathsOp_3` replaces. The grammar node itself, the 15 m expansion and the tag stay native
(the task's two `keep` generation nodes are `Assign_HighwayShapeGrammar` and `Subgraph_4`, and
`Subgraph_0`/`AddTag_Highway` are two one-node wrappers around engine elements). The whole pillar
chain is native too, because it is a `PCGProjectionSettings` onto a concrete surface and the contract
keeps the generation half.

The computation, each step naming the official nodes it replaces:

  1. **Read the two highway splines** -- `Subgraph_7 Get_ActorDataByRef` over the two
     `HighwaySpline2/3` actors. Measured 2026-10-17: two OPEN curves, 12 and 11 control points,
     8 652.68 m and 7 883.71 m long, every control point at Z 5550 -- they float 61.5 m above the
     city's flat terrain plane (Z -600), which is why the flatten and the projection are both needed.
  2. **Flatten** -- `AttributeMathsOp_0 "Flatten Spline to Z = 0"`: `$Position.Z <- 0`.
  3. **Resample at 80 m** -- `Subgraph_9 Transform_Resample` (`Distance` 8000, `SamplingMode`
     Distance, and the primitive's `InputsProcessingGraph` is `InputsProcessing_ForceSpline`). Its
     CoreProcess (`Transform_Resample_CoreProcess`, 15 nodes) is a `SplineSampler` in Distance mode
     with `DistanceIncrement` = 8000, then two `CreateSpline_0/1` (open and closed) and the two
     `AddTags` that mark `Type:Spline`. The sampler walks the CURVE, not the control points: 110 and
     100 points come out, against the control-point counts' 12 and 11. 80 m is the graph's own
     override, not the 40 m the brief mentions -- the brief's number is the node TITLE's
     ("Resample Spline (40m intervals)"), which the override does not follow.
  4. **Project onto the terrain** -- `Subgraph_8 Transform_Project` with `SecondaryInput` =
     `Subgraph_3 Get_MeshTerrain` (`MeshPartitionQueryType` Final, bounds 300 000 cm). Its CoreProcess
     is 129 nodes (a `SplineSampler`, a `SurfaceSampler` over a `CreateSurfaceFromPolygon2D`, a
     nearest-point projection, and a `Lerp` of `$Position.Z` by `ProjectAttribute`); the result is the
     spline's positions moved onto the terrain. The port reads the same surface through
     `pypcg.ue.terrain.Terrain.height`, the data's own `k2_sample_point` -- the same ray the
     `PCGMeshPartitionData` answers. Measured: the terrain under both highways is flat at Z -600.
  5. **Clamp, rebuild, level** -- `GetSplineControlPoints_0` reads the projected spline's control
     points; `AttributeMathsOp_1` clamps `$Position.Z` into [-500, 1e9]; `CreateSpline_0` builds a
     LINEAR spline from them; `AttributeMathsOp_2/3` set `$Rotation.Roll` and `$Rotation.Pitch` to 0.
     The port emits one `Spline` per highway on the `Highway` pin, at Z = -600 (the clamped terrain
     height), which is what the grammar node consumes.

The footprint the grammar node then builds is `Highway_Width` wide, and the published `Highway`
polygon is `Highway_Width + 3000` wide because `Subgraph_0` grows it by 1500 on each side. Measured
at three widths, the published area is linear in the parameter: 433 468 m2 at 2000, 606 862 m2 at
4000, 953 642 m2 at 8000, i.e. `(W + 3000) x L` to within 0.7 % -- which is how the port's own
`test_the_footprint_width_follows_the_parameter` pins the relationship.

Deliberate differences and what is not reproduced:

1. **The width convention: the offset argument is the band's FULL width.** `CreatePolygon2D`'s
   `OpenPolygonWidth` reaches `ClipperOffset` unchanged (`PCGCreatePolygon2D.cpp:256`,
   `PolygonOffsetUtils.cpp:52`), and Clipper halves it internally for every non-`Polygon` end type --
   `clipper.offset.cpp:415`: `if (group.end_type_ != EndType::Polygon) delta = std::abs(delta) / 2;`
   -- so an open-path offset of `W` puts a rail `W / 2` either side and the band is `W` across. The
   same argument therefore means the same thing in `Ops.path_offset` and in `CreatePolygon2D`: a
   100 000 cm path at 2000 comes back spanning `y = 2000`. A 36 118.85 cm path at 1900 gives 6 862.58
   m2, measured in the editor (2026-10-17). **No halving belongs at the call site.** The stage's
   published polygon is reproduced by `path_offset(path, W)` then `expand(1500)` to +0.10 % / +0.53 %
   on area and the same implied half-width as the official (2 485 / 2 486 cm), and its published width
   is `Highway_Width + 3000`. The port does not call any of this -- the grammar node, the expansion and
   the tag are native -- but the note records it because the V1 check has to know what a correct
   published width looks like and because stage 7 uses the same node.
2. **`Subgraph_6 "Filter: Road-Modified Terrain"` is not kept.** It filters the Roads actor output
   for the `ModifiedTerrain` tag and nothing reads it: it has no outgoing edge in the official graph.
   Keeping it would add a native node whose output the compiler culls.
3. **The two dropped parameters stay dropped.** `PartitionGridSize` feeds only the dropped
   `Subgraph_2 GridPartition` and `Loop_1`; `Partitioned` feeds only `Branch_0`, which is kept, so
   the slim graph declares it and leaves `Partitioned` false -- the value every volume this port runs
   uses -- the same way stage 7's slim graph handles its three kept branches.
4. **`Highway_Width`'s demo override is not an override at all.** `Tools/pypcg/data/demo_overrides.json`
   carries no `Highway_Width` entry for this stage (the generated brief prints `""` for "absent"), so
   the volume runs on the graph's own 2000. Measured 2026-10-17: setting the instance parameter to
   the empty string makes `apply_overrides` read back `0` -- an empty JSON value on a Double
   parameter is silently 0, not "leave it alone" -- so the slim graph must always ship the graph's
   own default, which it does (`Param(2000.0, ...)`).
"""
from pypcg import geo
from pypcg.geo import Spline
from pypcg.stage_api import Param

STAGE = 8
DOC = """Highways (高速): two highway spline actors flattened to Z 0, resampled every 80 m, projected
onto the final mesh terrain, clamped and rebuilt as level splines. Those splines feed the native
Assign_HighwayShapeGrammar node, which builds the Highway_Width footprint of each highway; the 15 m
expansion and the `Highway` tag stay native, as does the whole support-asset chain. Areas are in m2,
lengths in cm."""
# The official graph draws no random number anywhere on the read side; the pillar half is native.
RANDOM = False
PARAMS = {
    "Highway_Width": Param(2000.0, "Width of the generated highway in centimeters. Drives the Size "
                                   "parameter of the Assign_ShapeGrammarDefinition subgraph that runs "
                                   "SGD_ElevatedHighway", category=""),
    # Declared because the kept `Branch_0` tests it and a branch whose `bOutputToB` pin is unwired
    # has no defined output side. False is the value every profile this port runs uses.
    "Partitioned": Param(False, "dropped by the port contract; present only to drive the kept "
                                "Branch_0, and false on every volume this port runs", category=""),
}
INPUTS = {"HighwaySplines": "spline", "Roads": "any", "MeshTerrain": "surface"}
OUTPUTS = ("Highway",)

# `Subgraph_9 Transform_Resample`'s own override. The node's TITLE says 40 m; the override is 80 m
# and the override is what runs (measured: 110 and 100 samples over 8 652.68 m and 7 883.71 m).
RESAMPLE_DISTANCE_CM = 8000.0
# `AttributeMathsOp_1`'s two inline pin defaults.
CLAMP_MIN_CM = -500.0
CLAMP_MAX_CM = 1.0e9
# `Subgraph_0 Transform_Areas_Expand`'s own override, which the graph applies to the grammar node's
# footprint. The expansion itself stays native; the constant is here because it is the stage's, and
# the V1 check reads it to know the published width.
EXPAND_CM = 1500.0
# `Assign_HighwayShapeGrammar`'s `Size` pin is the band's FULL width, and the offset argument is that
# same full width: measured in the editor on a 36 118.85 cm straight path (2026-10-17),
# `OpenPolygonWidth` 1900 gives `36118.85 x 1900` cm, and Clipper halves the delta internally for an
# open path (`clipper.offset.cpp:415`). The offline stand-in in `Tools/pypcg/tests/fakes.py` takes the
# same full width, so all three agree. The width is the native grammar node's business here; the
# constant is recorded because the V1 check has to know what a correct published width looks like.
def published_width_cm(width):
    """The width of the polygon the stage publishes: the grammar node's `Highway_Width` footprint
    plus 1500 cm on each side. Measured at three widths: 433 468 m2 at 2000, 606 862 at 4000,
    953 642 at 8000, i.e. `(W + 3000) x L` to 0.7 %."""
    return float(width) + 2.0 * EXPAND_CM


def _xyz(p):
    """A (x, y, z) triple from any point-like tuple."""
    return (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)


def flatten(spline):
    """`AttributeMathsOp_0 "Flatten Spline to Z = 0"`: every point at Z 0. The dense polyline comes
    along, because the resample walks the curve, not the control points (8 652.68 m of curve against
    8 494.84 m through highway 2's 12 control points)."""
    if not spline.points:
        return None
    tangents = [(_xyz(a), _xyz(b)) for a, b in spline.tangents] if spline.tangents else None
    polyline = [(p[0], p[1], 0.0) for p in spline.polyline] if spline.polyline else None
    return Spline([(p[0], p[1], 0.0) for p in spline.points], spline.closed, spline.linear, tangents, polyline)


def curve_of(spline):
    """The curve as the engine samples it: the dense polyline when the value carries one, else the
    control points. A closed spline's polyline repeats its first vertex, which `drop_closing` drops."""
    pts = list(spline.polyline or spline.points)
    return [_xyz(p) for p in (geo.drop_closing(pts) if spline.closed else pts)]


def resample(path, distance_cm=RESAMPLE_DISTANCE_CM):
    """`Transform_Resample` in Distance mode over an open path: a point every `distance_cm` of
    arclength, the first point at 0, and the path's own end point. Measured against the engine's
    `get_location_at_distance_along_spline` at 8000 cm: 110 points for highway 2 and 100 for
    highway 3, exactly what this returns for both."""
    if len(path) < 2 or distance_cm <= 0.0:
        return list(path)
    out, carry = [path[0]], 0.0
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        seg = geo.path_length([(a[0], a[1]), (b[0], b[1])])
        d = 0.0
        while seg and carry + (seg - d) >= distance_cm:
            d += distance_cm - carry
            t = d / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t))
            carry = 0.0
        carry += seg - d
    if out[-1][:2] != path[-1][:2]:
        out.append(path[-1])
    return out


def project(points, surface):
    """`Subgraph_8 Transform_Project` with `bProjectPositions` on: move each point onto the surface.
    `surface` is anything with `height(x, y)` (the editor's terrain wrapper); a point the surface
    does not answer for keeps its own Z, which is what the node's `ProjectMask` does at a miss."""
    if surface is None or not hasattr(surface, "height"):
        return list(points)
    out = []
    for p in points:
        z = surface.height(p[0], p[1])
        out.append((p[0], p[1], p[2] if z is None else float(z)))
    return out


def clamp(points, lo=CLAMP_MIN_CM, hi=CLAMP_MAX_CM):
    """`AttributeMathsOp_1`: `Clamp` of `$Position.Z` with the node's own two inline defaults."""
    return [(p[0], p[1], min(max(p[2], lo), hi)) for p in points]


def level_spline(points, closed=False):
    """`CreateSpline_0` + `AttributeMathsOp_2/3`: a LINEAR spline through the points, with
    `$Rotation.Roll` and `$Rotation.Pitch` reset. A linear spline's tangents are its segments, so
    zeroing the two rotation components is what makes the ribbon follow the ground plane."""
    return Spline([(p[0], p[1], p[2]) for p in points], closed=closed, linear=True)


def highway_spline(spline, surface):
    """One highway spline through steps 2-5: flatten, resample, project, clamp, rebuild level."""
    flat = flatten(spline)
    if flat is None:
        return None
    path = resample(curve_of(flat))
    if len(path) < 2:
        return None
    return level_spline(clamp(project(path, surface)), closed=flat.closed)


def run(inputs, params, ctx):
    """One level spline per highway spline on the `HighwaySplines` pin, all on the `Highway` pin.

    The pin is a single one because the official `Subgraph_7 Get_ActorDataByRef` reads BOTH spline
    actors in one node and hands its whole output to `AttributeMathsOp_0`: two pins fed from the same
    node would see the same two splines twice, and the stage would publish four footprints instead of
    two (measured 2026-10-17 on the first slim run).

    `MeshTerrain` is the surface to project onto. `Roads` is not an input of this computation: the
    kept native `Subgraph_1 Filter_Tags 'RoadFootprints'` reads the Roads actor directly. It is on the
    contract because the stage reads it, and it stays wired in the slim graph because an unwired
    dynamic pin culls the Python node.
    """
    out = {"Highway": []}
    surfaces = [v for v, _ in inputs.get("MeshTerrain", []) if hasattr(v, "height")]
    surface = surfaces[0] if surfaces else None
    for value, _tags in inputs.get("HighwaySplines", []):
        if not isinstance(value, Spline):
            continue
        line = highway_spline(value, surface)
        if line is not None:
            out["Highway"].append((line, ["Highway"]))
    return out
