"""Stage 7 -- Roads (PCG_3_1_2_Roads, 道路). Both halves.

The official graph is 210 nodes, 136 of them computation; most of that computation hides inside the
subgraphs it calls (`Intersection_solving` 170 nodes, `Crosswalks` 75, plus the PCGPrimitives
outline/boolean/placement primitives). This module ports the two halves that are computation:

  1. THE FOOTPRINT -- the stage's published `RoadFootprints`, a union of ribbons over the Districts'
     OWN road lines. The union of the three classes' ribbons, each line extended by half its class
     width, plus the Landmarks ring in the local class. `pypcg.geo.roads`.
  2. THE SECTIONS -- `Intersection_solving`: each class's centerline split into the pieces between
     intersections, the pieces inside them, and the intersection planes themselves. Everything after
     it in the stage reads this, so it is what makes the rest of the graph run. `pypcg.geo.sections`.

The other reads of the graph -- `Crosswalks` (75 nodes), the six `Assign_ShapeGrammarDefinition`
nodes and the two `Write_MeshTerrain` nodes -- stay engine nodes by contract (Ruling 2): they are
kept by name in the slim graph and fed from this module's outputs.

Reading the graph top to bottom:

  Subgraph_0 (Districts) -> FilterDataByTag_3/4/5 (localRoads / CollectorRoads / ArteryRoads)
    -> Subgraph_86/87/88 (Transform_Outline, width = that class's width)
    -> Subgraph_89 (Compose_Areas_Union) -> AddTags_1 "RoadFootprints"
    -> AddAttribute_2/1/0 (embed LocalWidth / CollectorWidth / ArteryWidth) -> output

with `Subgraph_86` taking the "Landmarks" spline on a second `PrimaryInput` (that spline is
`Subgraph_24 Transform_Areas_Expand(800)` over MainTower and CentralParkFootprint, and it is the only
extra input any of the three outline nodes has).

The footprint is therefore the union of the three classes' ribbons taken from the DISTRICTS output,
not from the solved sections: the `Stripe Pass` filters read the Districts actor data while the
solved sections are declared separately (`NamedRerouteDeclaration_0/4/5`). `Intersection_solving`
then does its own, different thing with the same lines -- it publishes its own `RoadsFootprints`,
which nothing at stage level reads, and the sections, which the six grammar nodes, the decals, the
road mesh, the crosswalks and the terrain flattening all read.
"""
from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.stage_api import Param

STAGE = 7
DOC = """Roads (道路): the road footprint of the three classes and the solved road sections. The
footprint is the union of the three class ribbons (widths local_Width, collector_width,
Artery_width) outlined around the Districts' own road lines, the Landmarks ribbon joining the local
class; it is published tagged RoadFootprints with the three widths embedded. The sections half
reproduces Intersection_solving: each class's centerlines split into the pieces between intersections
(roadSections) and the pieces inside them (intersections / intersectionsShort), plus the intersection
planes, all of which the stage's grammar, decal, road-mesh and crosswalk nodes consume. Areas and
lengths are in m2 / m, widths in cm."""
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
    # The contract DROPS this one, but three kept branches (`Branch_15/16/18`) test it and a branch
    # with an unwired `bOutputToB` has no defined output side, so the graph needs the parameter to
    # exist. It stays false everywhere, which is what every volume this port runs sets it to, so only
    # the `Output A` side -- the three `Spawn_Assets` nodes and the road-mesh branch -- is ever taken.
    "Partitioned": Param(False, "dropped by the port contract; present only to drive the three kept "
                                "branches that test it, and false on every volume this port runs",
                         category="Partition"),
}
INPUTS = {"Districts": "any", "MainTower": "polygon", "CentralParkFootprint": "polygon"}
OUTPUTS = ("RoadFootprints", "LocalSections", "CollectorSections", "ArterySections",
           "IntersectionsPlanar", "Landmarks", "LocalRoads", "CollectorRoads", "ArteryRoads")
# The one output that stays INSIDE this module. `Landmarks` is the ring `Subgraph_24`/`CreateSpline_0`
# builds; in the official graph it is declared by `NamedRerouteDeclaration_2` and read by `Subgraph_86`
# (the local outline), `Subgraph_27/28/13` (the three landmark clips) and `Subgraph_3` (the segment
# split) -- but every one of those readers is itself ported here, so no KEPT native node consumes it.
# It is still published (the checks and the tests read it) and the slim graph wires it: see
# `dsl.SlimGraph`, which emits a pin for every `OUTPUTS` entry.
INTERNAL = ("Landmarks",)

# `Transform_Outline`'s Width pin per class, and `AddAttribute_*`'s attribute name per class.
CLASS_WIDTH = (("localRoads", "local_Width", "LocalWidth"),
               ("CollectorRoads", "collector_width", "CollectorWidth"),
               ("ArteryRoads", "Artery_width", "ArteryWidth"))

# `Subgraph_24 Expand Footprints by Half width of local roads`: Expand = 800 (the graph's override).
# This is the Landmarks branch -- `Subgraph_24` -> `FilterDataByType_5` -> `GetSplineControlPoints_0`
# -> `CreateSpline_0` -> `NamedRerouteDeclaration_2 "Landmarks"`, whose only outline consumer is
# `Subgraph_86` (the local class). Nothing here goes through `Subgraph_3 Extract Road Segments`: that
# node reads the same Landmarks declaration but feeds `Gather_0` -> `Subgraph_2 Intersection_solving`,
# i.e. the SECTIONS, which is the sections half's input and not the footprint's.
LANDMARK_EXPAND = 800.0

# `Intersection_solving`'s `roadSectionLimit` and `intersection_expansion_range`. The limit is the
# graph's own default (200) on every path; the expansion range is overridden to 50 in the demo level
# against a graph default of 100, and the sections port is measured against a run of the real
# primitive on the demo level's own inputs, so 50 is its default here.
SECTION_LIMIT = 200.0
EXPANSION_RANGE = 50.0


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
    local road lines on one `PrimaryInput` edge and the Landmarks on a second. The sections half
    reads the same ring again, as the cutter for `Subgraph_27/28/13 Clip ... At Landmark`."""
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
            parts += geo.roads.outline(path, width, ops) if not _is_ring(path) \
                else geo.roads.outline_ring(path[:-1], width, ops)
    local_width = float(params["local_Width"])
    for ring in landmarks(inputs, params, ops):
        parts += geo.roads.outline_ring(ring.outer, local_width, ops)
    return geo.roads.union(parts, ops)


def _is_ring(path):
    return len(path) > 2 and abs(path[0][0] - path[-1][0]) < 1e-6 and abs(path[0][1] - path[-1][1]) < 1e-6


def class_paths(inputs, ops, params):
    """The three road classes as the SECTIONS half needs them: clipped at the landmark.

    `Intersection_solving` receives, per class, the Districts' lines of that class minus the
    Landmarks ribbon (`Subgraph_27 Clip Collector Roads At Landmark`, `Subgraph_28 Clip Local Roads At
    Landmark`, `Subgraph_13 Clip Roads At Landmark Boundary`), and the LOCAL class additionally
    receives the Landmarks ring's own edges (`Subgraph_3 Extract Road Segments`,
    `CutAngleThreshold = 3`, gathered with `Subgraph_27`'s output into `Gather_0`).

    The three subtractions are Difference `Compose_Spline_Cut`s, and `Subgraph_3`'s
    `Extract_Segments` reads the same closed landmark ring, splitting it at bends over 3 degrees.
    Both are pure geometry: `clip_path(..., keep_inside=False)` subtracts the ring, and
    `extract_segments` splits it."""
    rings = landmarks(inputs, params, ops)
    cutters = [r.outer for r in rings]
    out = {}
    for tag in geo.sections.CLASSES:
        out[tag] = []
        for path in _class_lines(inputs, tag):
            out[tag] += geo.sections.cut_paths([path], cutters, ops, inside=False)
    # `Gather_0`'s second input: the landmark ring's own segments, added to the LOCAL class only.
    # `Subgraph_3 Extract Road Segments` reads the Landmarks ring and splits it at bends over 3
    # degrees, so what it contributes is a LIST of segments, not one path.
    for ring in rings:
        for seg in geo.extract_segments(list(ring.outer) + [ring.outer[0]], LANDMARK_CUT_ANGLE):
            out[geo.sections.LOCAL] += geo.sections.cut_paths([seg], cutters, ops, inside=False)
    return out


LANDMARK_CUT_ANGLE = 3.0


def _class_lines(inputs, tag):
    """One class's lines from the Districts data, closed rings included and not extended.

    `Intersection_solving` extends its classes itself (`Subgraph_1/2/3`), on input that the landmark
    clip has already shortened, so this returns the lines as the clip receives them -- extended by
    nothing. A closed ring is carried as a ring rather than an extended line, which is the same rule
    `_paths` uses for the footprint.

    No width parameter: the decal chain reads these lines RAW (`FilterDataByTag_6/10/11` sit ahead of
    `Subgraph_1/2/3` on the same `Reroute_4` carrier), so nothing here depends on the class width."""
    out = []
    for value, tags in inputs.get("Districts", []):
        if isinstance(value, Spline) and tag in tags:
            path = geo.roads.path_of(value)
            if value.closed:
                out.append(path + [path[0]])
            else:
                out.append(path)
    return out


def sections(inputs, params, ops):
    """The sections half: `Intersection_solving` over the landmark-clipped classes."""
    return geo.sections.solve(class_paths(inputs, ops, params),
                              dict(params, roadSectionLimit=SECTION_LIMIT,
                                   intersection_expansion_range=EXPANSION_RANGE), ops)


def _xyz(path):
    """A path as `Spline` points, 3D. `Spline` always wants an XYZ tuple, while the geometry layer
    now preserves the input's arity (2D in, 2D out), so the Z is supplied HERE -- at the one boundary
    that needs it -- rather than inside the geometry, where forcing it broke stage 6."""
    return [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in path]


def run(inputs, params, ctx):
    """The footprint, the sections, and the three intermediates the kept native nodes read.

    Six output pins, in the order the official graph uses them:

      RoadFootprints        the contract's first output (`AddTags_1`)
      LocalSections         `Branch_0`/`Branch_3`/`Branch_9`/`Branch_11` -- the grammar filter, the
                            crosswalk filter, the road-mesh place-on-spline and the crosswalk branch
      CollectorSections     `Branch_1`/`Branch_4`/`Branch_10` and the same four
      ArterySections        `Branch_2`/`Branch_5`/`Branch_12` and the same four
      IntersectionsPlanar   `Subgraph_31 Project Intersections To Terrain`, the start of the
                            intersection-flatten chain
      Landmarks             the ring `Subgraph_24`/`CreateSpline_0` builds, which the three landmark
                            clips cut against and `Subgraph_3` splits into segments
      LocalRoads / CollectorRoads / ArteryRoads
                            the landmark-clipped classes, which `Branch_6/7/8` places the spray-paint
                            decals along (the decal chain reads the lines, the grammar reads the
                            solved sections)

    `ModifiedTerrain` is NOT an output: the two `Write_MeshTerrain` nodes stay native and the graph
    publishes the stage's second output from them, exactly as the official graph does.
    """
    # Every pin exists on every run, empty or not: the slim graph wires all nine, and a missing pin
    # would leave a kept native node with no input rather than with an empty one.
    out = {pin: [] for pin in OUTPUTS}
    for p in outline_union(inputs, params, ctx.ops):
        out["RoadFootprints"].append((p, ["RoadFootprints"]))
    classes = class_paths(inputs, ctx.ops, params)
    solved = geo.sections.solve(classes, dict(params, roadSectionLimit=SECTION_LIMIT,
                                             intersection_expansion_range=EXPANSION_RANGE), ctx.ops)
    for tag, pin in ((geo.sections.LOCAL, "LocalSections"),
                     (geo.sections.COLLECTOR, "CollectorSections"),
                     (geo.sections.ARTERY, "ArterySections")):
        out[pin] = [(Spline(_xyz(path), linear=True), [label])
                    for path, label in solved["sections"][tag] if len(path) >= 2]
    out["IntersectionsPlanar"] = [(p, ["IntersectionsPlanar"]) for p in solved["planar"]]
    out["Landmarks"] = [(Polygon(list(r.outer)), ["Landmarks"]) for r in landmarks(inputs, params, ctx.ops)]
    # The three classes as the DECAL chain reads them: the Districts' own lines of that class, NOT
    # clipped at the landmark. `FilterDataByTag_6/10/11` sit ahead of the three clips
    # (`Subgraph_27/28/13`) on the same `Reroute_4` carrier, so the decals are placed along the full
    # line while the grammar gets the solved, landmark-clipped sections.
    for tag, pin in ((geo.sections.LOCAL, "LocalRoads"), (geo.sections.COLLECTOR, "CollectorRoads"),
                     (geo.sections.ARTERY, "ArteryRoads")):
        out[pin] = [(Spline(_xyz(path), closed=_is_ring(path), linear=True), [tag])
                    for path in _class_lines(inputs, tag)
                    if len(path) >= 2]
    return out
