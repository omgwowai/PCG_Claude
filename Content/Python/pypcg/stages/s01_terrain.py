"""Stage 1 -- Terrain (PCG_1_1_Terrain, 地形底座): the masks.

The island the city stands on. The official graph is 20 nodes (13 of them computation); `docs/pypcg/stages/s01.md`
names the official node behind every step. This is the FIRST of two Python nodes: the two areas the native
projections flatten towards. The per-point work between them stays native, on measured timings (s01.md 0):

  FOOTPRINT   the base terrain's extracted points [ExtractMeshTerrainPoints_0, kept] combined into one box
              [Subgraph_1 Extract_Bounds: every point's own box, rotated, in one FBox], whose rectangle at the
              box's TOP is the terrain's footprint [TraceBoundFootprint_TerrainShaping1 Trace_Bound_Footprint,
              PlanarSurface Top] -- `geo.ground.bounds_footprint`, stage 18's helper
  SQUARE      grown 600 m [Subgraph_2 Transform_Areas_Expand, Expand 60000] and moved down 1820.424606 cm
              [Subgraph_0 Transform_Offset, PerPoints false]
  CIRCLE      the Terrain_shaping_1 outline [GetActorData_TerrainShaping1, kept], moved down the same
              [Subgraph_6 Transform_Offset]: only its outline is used next
  ANNULUS     the square less the circle [ComposeExclusion_SquareMinusCircle Compose_Areas_Exclusion]
              -> `FlattenArea`, the area native `FlattenProject_AroundCircle` pulls the hills down to
  CITY ZONE   the City outline [Subgraph_3, kept] with every control point's world z set to 0
              [AttributeMathsOp_2 Set $Position.Z] and lifted 3000 cm [Subgraph_4 Transform_Offset]
              -> `CityFlatZone`, the curve native `Subgraph_5` turns into a polygon and flattens the city to

Kept native after this node (s01.md 0, Step F): SpatialNoise_Hills (its blur: 445 s in Python),
FlattenProject_AroundCircle and Subgraph_5 (the GPU nearest-target projection: 36 s each in Python, and one
float32 ulp off on 5 % of the points). `s01_terrain_blend` does the Lerp after them.
"""
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import ground as G

STAGE = 1
DOC = """Terrain (地形底座): the base mesh terrain's points get native hills noise; everything outside the
Terrain_shaping_1 circle is pulled down to a flat floor (the terrain's footprint grown 600 m, less the circle,
1820 cm below the footprint's top) with a 500 m falloff, the city footprint is flattened to 3000 cm with a 100 m
falloff, and the two are blended by 1 - CityFlatness before the terrain is written back."""
RANDOM = False
PARAMS = {}
INPUTS = {"MeshTerrain": "points", "TerrainShaping": "spline", "City": "spline"}
OUTPUTS = ("FlattenArea", "CityFlatZone")

EXPAND_CM = 60000.0                    # Subgraph_2 "Expand Footprint 600m"
DOWN_CM = -1820.424606                 # Subgraph_0 "Offset Footprint Down", Subgraph_6 "Offset Circle Down"
CITY_UP_CM = 3000.0                    # Subgraph_4 "Move City Shape Up"
CITY_Z_CM = 0.0                        # AttributeMathsOp_2 Set $Position.Z (InB's default value)


def footprint(points):
    """`(x0, y0, x1, y1, z)` of the extracted points at the box's top, or None."""
    return G.bounds_footprint(points, G.PLANE_TOP)


def square(fp, ops):
    """The footprint grown 600 m and moved down: one Polygon, or [] without a footprint."""
    if fp is None:
        return []
    x0, y0, x1, y1, z = fp
    grown = A.expand([Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)], EXPAND_CM, ops)
    return [Polygon(p.outer, p.holes, z + DOWN_CM) for p in grown]


def circles(items):
    """The Terrain_shaping_1 outlines as areas (a closed spline's polyline; `Subgraph_6`'s offset only moves z)."""
    return A.areas_of(items)


def flatten_area(fp, shaping, ops):
    """`FlattenArea`: the grown, lowered footprint less every Terrain_shaping_1 outline, at the square's z."""
    sq = square(fp, ops)
    if not sq:
        return []
    z = sq[0].z
    return [Polygon(p.outer, p.holes, z) for p in A.exclusion(sq, circles(shaping), ops)]


def city_flat_zone(items):
    """`CityFlatZone`: each City spline with its control points' WORLD z set to 0 (`$Position` on a spline is
    the control points in world coordinates) and lifted 3000 cm. Positions in x, y, the tangents (a z move leaves
    them), the closed and linear flags and the control-point rotations are the input's."""
    out = []
    for v, _tags in items:
        if not isinstance(v, Spline) or not v.points:
            continue
        pts = [(p[0], p[1], CITY_Z_CM + CITY_UP_CM) for p in v.points]
        out.append(Spline(pts, closed=v.closed, linear=v.linear, tangents=v.tangents,
                          rotations=v.rotations))
    return out


def masks(inputs, ops):
    points = [v for v, _t in inputs.get("MeshTerrain", []) if isinstance(v, Points)]
    fp = footprint(points)
    notes = []
    if fp is None:
        notes.append("no terrain points: no footprint, no flatten area")
    else:
        notes.append("footprint %r %r %r %r %r (%d points)" % (fp + (sum(len(p) for p in points),)))
    area = flatten_area(fp, inputs.get("TerrainShaping", []), ops)
    zone = city_flat_zone(inputs.get("City", []))
    notes.append("flatten area: %d polygons, %s holes, %.3f m2" % (
        len(area), [len(p.holes) for p in area], sum(A.area_cm2(p) for p in area) / 1e4))
    notes.append("city flat zone: %d splines" % len(zone))
    return area, zone, notes


def run(inputs, params, ctx):
    area, zone, notes = masks(inputs, ctx.ops)
    ctx.notes += notes
    return {"FlattenArea": [(p, ["FlattenArea"]) for p in area],
            "CityFlatZone": [(s, ["CityFlatZone"]) for s in zone]}
