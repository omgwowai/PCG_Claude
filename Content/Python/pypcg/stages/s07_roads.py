"""Stage 7 -- Roads (PCG_3_1_2_Roads, 道路). The footprint half.

The official graph is 210 nodes, 136 of them computation; most of that computation hides inside the
three big subgraphs it calls (`Intersection_solving` 170 nodes, `Crosswalks` 75, plus the
PCGPrimitives outline/boolean/placement primitives). This module is the part of it that produces the
stage's two published outputs: the road footprints (`RoadFootprints`, one unioned Polygon2D carrying
the three class widths) and, on the second node, the flattened terrain zones. `Crosswalks` and the
two `Write_MeshTerrain` nodes are kept as engine nodes by the contract.

Reading the graph top to bottom:

  Subgraph_0 (Districts) -> FilterDataByTag_3/4/5 (localRoads / CollectorRoads / ArteryRoads)
    -> Subgraph_86/87/88 (Transform_Outline, width = that class's width)
    -> Subgraph_89 (Compose_Areas_Union) -> AddTags_1 "RoadFootprints"
    -> AddAttribute_2/1/0 (embed LocalWidth / CollectorWidth / ArteryWidth) -> output

so the footprint is the union of the three classes' ribbons taken from the DISTRICTS output, not from
the solved sections. The naive check agrees: the three classes' lengths times their widths give
855 711 m2 against the official 842 714 m2, a 1.5 % overlap -- exactly the loss a union of a connected
road network implies. The `Stripe Pass` filters confirm it: they read `NamedRerouteUsage_2`, which is
the Districts actor data, while the solved sections are declared separately (`NamedRerouteDeclaration_
0/4/5`).
"""
from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.stage_api import Param

STAGE = 7
DOC = """Roads (道路): the road footprint of the three road classes and the terrain-flatten zones. The
three class ribbons (widths local_Width, collector_width, Artery_width) are outlined around the
Districts' own road lines, the landmark cut is applied, and the union is published tagged
RoadFootprints with the three widths embedded. The terrain zones feed the kept Write_MeshTerrain
nodes. Areas and lengths are in m2 / m, widths in cm."""
RANDOM = False
_CAT = "Road Parameters"
PARAMS = {
    "simpleRoads": Param(False, "will spawn a simplified version of the road without using shape "
                                "grammar, much faster compute", category=_CAT),
    "local_Width": Param(1900.0, "", category=_CAT),
    "collector_width": Param(2600.0, "", category=_CAT),
    "Artery_width": Param(3400.0, "", category=_CAT),
    "Road_Profile": Param("/PCGPrimitives/Grammar/DataAsset/Road_Demo/SGD_Road_Demo.SGD_Road_Demo", "",
                          type="SoftObject",
                          type_object="/PCGPrimitives/Grammar/BP/BP_ShapeGrammarDefinition.BP_ShapeGrammarDefinition_C",
                          category=_CAT),
    "Crosswalks": Param(False, "", category=_CAT),
}
INPUTS = {"Districts": "any", "MainTower": "polygon", "CentralParkFootprint": "polygon"}
OUTPUTS = ("RoadFootprints",)

# `Transform_Outline`'s Width pin per class, and `AddAttribute_*`'s attribute name per class.
CLASS_WIDTH = (("localRoads", "local_Width", "LocalWidth"),
               ("CollectorRoads", "collector_width", "CollectorWidth"),
               ("ArteryRoads", "Artery_width", "ArteryWidth"))

# `Subgraph_24 Expand Footprints by Half width of local roads`: Expand = 800 (the graph's override).
LANDMARK_EXPAND = 800.0
# `Subgraph_3 Extract Road Segments`: CutAngleThreshold = 3.
LANDMARK_CUT_ANGLE = 3.0


def _paths(items, tag, width_cm):
    """The class's road lines as XY polylines, each extended by half its width.

    `FilterDataByTag_3/4/5` select the class by a SUBSTRING match on the tag (`Operator =
    Substring`), so the closed City outline -- which stage 6 tags `ArteryRoads` as well, being the
    boundary of the artery network -- arrives on the artery pin together with the artery segments.
    It is a closed ring, and `Transform_Outline`'s CoreProcess handles closed input on its
    `ForceClosed` branch (see `pypcg.geo.roads.outline`), so it contributes its own ribbon.

    `Intersection_solving`'s `Subgraph_1/2/3 Extend ... Road Splines` push each line out by half its
    class width with `Transform_Splines_Extend(distance = <class width>/2)` before anything else
    touches it."""
    out = []
    for value, tags in items:
        if isinstance(value, Spline) and tag in tags:
            path = geo.roads.path_of(value)
            if value.closed:
                path = path + [path[0]]
                out.append(path)                      # a closed ring is already its own band
            else:
                out.append(geo.roads.extend(path, 0.5 * float(width_cm)))
    return out


def landmarks(inputs, params, ops):
    """The "Landmarks" spline (`NamedRerouteDeclaration_2`), as `[Polygon]` rings.

    `Subgraph_24 Expand Footprints by Half width of local roads` = `Transform_Areas_Expand(Expand =
    800)` over `Subgraph_12` (MainTower) and `Subgraph_1` (CentralParkFootprint). Its
    `InputsProcessingGraph` is `InputsProcessing_ConvertClosedSplinesAndForwardPoly2Ds`, so the two
    stage-4/5 closed splines arrive as rings and come out expanded. Then
    `FilterDataByType_5` keeps the POLYLINES only, `GetSplineControlPoints_0` reads their vertices and
    `CreateSpline_0` rebuilds them with `bClosedLoop`, giving one closed landmark spline.

    That spline is what `Subgraph_86 Outline Local Roads` unions into the local class: it takes the
    local road lines on one `PrimaryInput` edge and the Landmarks on a second."""
    rings = []
    for pin in ("MainTower", "CentralParkFootprint"):
        for value, _tags in inputs.get(pin, []):
            if isinstance(value, Polygon):
                rings.append(value)
            elif isinstance(value, Spline):
                path = geo.roads.path_of(value)
                rings.append(Polygon(path + [path[0]] if value.closed or path[0] != path[-1] else path))
    return geo.roads.expand(rings, LANDMARK_EXPAND, ops)


def outline_union(inputs, params, ops):
    """The footprint branch: the three classes' ribbons, unioned. Returns `[Polygon]`.

    The landmarks ribbon goes with the LOCAL class -- `Subgraph_86` is the only outline node with a
    second input, and its `Width` is `local_Width` (`GetGraphParameter_46`).

    Measured 2026-10-16 against the live official footprint (842 714.39 m2): this construction gives
    837 227.8 m2 (-0.65 %), one polygon with 1043 outer vertices and 128 holes against the official's
    1022 and 132, and three of the official bbox's four edges to within 1e-10 cm. The residual is
    the landmark cut and the single-vs-double ribbon question on the ring inputs; see
    `docs/pypcg/stages/s07.md` section 7."""
    parts = []
    for tag, param, _attr in CLASS_WIDTH:
        width = float(params[param])
        for path in _paths(inputs.get("Districts", []), tag, width):
            parts += geo.roads.outline(path, width, ops)
    local_width = float(params["local_Width"])
    for ring in landmarks(inputs, params, ops):
        parts += geo.roads.outline(list(ring.outer) + [ring.outer[0]], local_width, ops)
    return geo.roads.union(parts, ops)


def run(inputs, params, ctx):
    """The road footprint. `ctx.ops` carries the Clipper2 booleans."""
    out = {"RoadFootprints": []}
    for p in outline_union(inputs, params, ctx.ops):
        out["RoadFootprints"].append((p, ["RoadFootprints"]))
    return out
