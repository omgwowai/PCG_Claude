"""Stage 18 -- OuterForest (PCG_5_2_OuterForest, 外围林地).

A dense forest scattered over the whole terrain outside the city, which fades in size and density towards the
water. The official graph is 67 nodes (47 of them computation); `docs/pypcg/stages/s18.md` names the official
node behind every step. This is the FIRST of two Python nodes: everything up to the scatter. The two texture
writes that follow stay native, and `s18_outer_forest_trees` does the rest.

The chain (official node names in brackets):

  FOOTPRINT   the final mesh terrain's points [Subgraph_7 Extract_MeshTerrainPoints, kept] combined into one
              box [Subgraph_8 Extract_Bounds: every point's own box, rotated, in one FBox], whose rectangle at the
              box's middle height is the terrain's footprint [Subgraph_9 Trace_Bound_Footprint, CenterPlaneZ,
              counter-clockwise]
  CITY        the City outline [Subgraph_6] grown by half the artery width plus CityEdgeBuffer [Subgraph_3,
              ExtractAttributeAtIndex_0 / AttributeMathsOp_1 / AttributeMathsOp_CityBuffer -- the artery width is
              read natively off the road footprint, as stage 10 does], in the outline's own polygon frame
  LESS CITY   the footprint less the grown city [ExcludeCity_0]
  LESS PARK   that less the central park grown by ParkBuffer [Subgraph_16, Subgraph_5] and less the highway
              polygons [Subgraph_0 Get Highway Volume, Reroute_1] -- one clip union [Subgraph_1]
  SCATTER     TreeDensity points per m2 [FillRandomly_0 Fill_Areas_Randomly: one point per grid cell of
              sqrt(1e4 / TreeDensity) cm, jittered, kept inside; `geo.ground.fill_random`, Python's numbers]
              -> `ForestPoints` -> the native texture writes [Subgraph_12, Subgraph_2] -> `s18_outer_forest_trees`

The roads are NOT subtracted: `Subgraph_4 Get Roads` is read only for its `ArteryWidth`. `Subgraph_13 Get City
Layout Volume` (the `Terrain` role) is read officially and has no user; the slim graph keeps it unwired.
"""
from pypcg import geo
from pypcg.geo import Points, Polygon
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stage_api import Param

STAGE = 18
DOC = """OuterForest (外围林地): the final terrain's footprint less the city (grown by half the artery width
plus CityEdgeBuffer), the central park (grown by ParkBuffer) and the highway, scattered with TreeDensity points
per m2; the native texture writes give each point a scale (ScaleMin..ScaleMax) and a species index; the trees
are kept near the shore and on land, shrink towards the water and take the tree mesh their index names."""
RANDOM = True
PARAMS = {
    "TreeDensity": Param(0.005, "Number of trees per square meter.", type="Double"),
    "CityEdgeBuffer": Param(100.0, "Distance (cm) kept clear between the city's edge road and the forest, on "
                                   "top of half the artery width", type="Float"),
    "ParkBuffer": Param(1900.0, "Distance (cm) kept clear around the central park", type="Float"),
}
INPUTS = {"MeshTerrain": "points", "City": "spline", "CentralParkFootprint": "spline", "Highways": "polygon",
          "ArteryWidth": "param"}
OUTPUTS = ("ForestPoints",)

CITY_EXPAND_DEFAULT_CM = 3400.0        # Subgraph_3's own Expand override, used when the pin gets no value
POINT_EXTENT_CM = 10.0                 # Fill_Areas_Randomly OutputPointsExtents (default)


def _first_number(items):
    for v, _tags in items:
        if isinstance(v, geo.ParamSet):
            for x in v.values.values():
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    return float(x)
    return None


def _world_box(pts, i):
    """`geo.ground.point_world_box` (moved there for stage 1, Task 24; this name stays for the fixture tool)."""
    return G.point_world_box(pts, i)


def footprint(sets):
    """`Subgraph_8 Extract_Bounds` + `Subgraph_9 Trace_Bound_Footprint` (`CenterPlaneZ`): the box's four corners
    at its middle height. `geo.ground.bounds_footprint(sets, 0.5)` -- the helper moved there unchanged when stage 1
    needed it with its `Top` plane (Task 24). `(x0, y0, x1, y1, z)` or None."""
    return G.bounds_footprint(sets, 0.5)


def footprint_polygon(fp):
    x0, y0, x1, y1, z = fp
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


def read(inputs):
    return {"terrain": [v for v, _t in inputs.get("MeshTerrain", []) if isinstance(v, Points)],
            "city": A.areas_of(inputs.get("City", [])),
            "park": A.areas_of(inputs.get("CentralParkFootprint", [])),
            "highway": A.areas_of(inputs.get("Highways", [])),
            "artery": _first_number(inputs.get("ArteryWidth", []))}


def city_buffer(artery, params):
    """`AttributeMathsOp_1` (ArteryWidth / 2) + `AttributeMathsOp_CityBuffer` (+ CityEdgeBuffer) into
    `Subgraph_3`'s `Expand` pin; no road footprint, no value on the pin, and the node's own 3400 applies."""
    if artery is None:
        return CITY_EXPAND_DEFAULT_CM
    return artery / 2.0 + float(params["CityEdgeBuffer"])


def forest_areas(fp, src, params, ops):
    """`ExcludeCity_0` then `Subgraph_1`: the footprint less the grown city, less the grown park and the
    highway. Returns `(areas, grown_city, grown_park)`."""
    if fp is None:
        return [], [], []
    buf = city_buffer(src["artery"], params)
    grown_city = []
    for c in src["city"]:
        grown_city += A.in_frame(c, lambda p: A.expand([p], buf, ops))
    grown_park = A.expand(src["park"], float(params["ParkBuffer"]), ops)
    less_city = A.exclusion([footprint_polygon(fp)], grown_city, ops)
    areas = A.exclusion(less_city, grown_park + src["highway"], ops)
    return [Polygon(p.outer, p.holes, fp[4]) for p in areas], grown_city, grown_park


def scatter(areas, density, rng):
    """`FillRandomly_0 Fill_Areas_Randomly` on each area: one point set per area that holds a point, each point
    with the primitive's box (+-10 cm), steepness 1, a seed of Python's own; density 1 (the sampler's density
    is overwritten before anything reads it: `CopyAttributes_0` in the shore step)."""
    e = POINT_EXTENT_CM
    out = []
    for a in areas:
        locs = G.fill_random(a, density, rng)
        if not locs:
            continue
        pts = Points()
        for p in locs:
            pts.add(p, bounds_min=(-e, -e, -e), bounds_max=(e, e, e), steepness=1.0,
                    seed=AS._i32(rng.getrandbits(32)))
        out.append(pts)
    return out


def forest(inputs, params, ops, rng):
    """The whole computation: (point sets, notes)."""
    src = read(inputs)
    fp = footprint(src["terrain"])
    areas, _city, _park = forest_areas(fp, src, params, ops)
    sets = scatter(areas, float(params["TreeDensity"]), rng)
    notes = []
    if fp is None:
        notes.append("no terrain points: no footprint, no forest")
    else:
        notes.append("footprint %r %r %r %r %r" % fp)
        notes.append("areas %d, %.6f m2; city expand %r cm" % (len(areas), sum(A.area_cm2(a) for a in areas) / 1e4,
                                                             city_buffer(src["artery"], params)))
        notes.append("scatter %d points in %d sets" % (sum(len(s) for s in sets), len(sets)))
    return sets, notes


def run(inputs, params, ctx):
    sets, notes = forest(inputs, params, ctx.ops, ctx.rng)
    ctx.notes += notes
    return {"ForestPoints": [(s, ["ForestPoints"]) for s in sets]}
