"""Slim graph of stage 1, Terrain (spec 2.4).

Two Python nodes: `s01_terrain` (the masks: the flatten area and the city flat zone) and `s01_terrain_blend`
(the `CityFlatness` blend), with the official per-point nodes kept native between them (s01.md 0, Step F on
measured timings: the hills noise's blur 445 s in Python, each GPU projection 36 s):

  GetMeshTerrain_0 (Base, sub-priority 1) -> ExtractMeshTerrainPoints_0 -+-> s01_terrain.MeshTerrain
                                                                          +-> SpatialNoise_Hills (NoiseAmplitude
                                                                              from the HillsHeight getter)
  GetActorData_TerrainShaping1 -> s01_terrain.TerrainShaping;   Subgraph_3 (City) -> s01_terrain.City
  SpatialNoise_Hills -> FlattenProject_AroundCircle (SecondaryInput <- FlattenArea)
                     -> Subgraph_5 Project City Flat Zone (SecondaryInput <- CityFlatZone)
  FlattenProject_AroundCircle -> s01_terrain_blend.Hills;   Subgraph_5 -> s01_terrain_blend.City
  s01_terrain_blend.Terrain -> WriteMeshTerrain_0 (sub-priority 1) -> the graph output, as officially

What differs from the official wiring: `GetParam_CityFlatness` -> `AttributeMathsOp_1` -> `AttributeMathsOp_0`'s
Ratio is the blend node's own `CityFlatness` getter; the ten mask and blend nodes are the two Python nodes.
"""
from pypcg import dsl
from pypcg.stages import s01_terrain as S
from pypcg.stages import s01_terrain_blend as B


def build():
    g = dsl.SlimGraph(S, extra_params=(dsl.official_param(S.STAGE, "HillsHeight"),), more_modules=(B,))
    blend = g.pynodes["s01_terrain_blend"]

    # ---- the scene reads ----
    terrain = g.keep("GetMeshTerrain_0")                                   # Get Mesh Terrain (Base)
    points = g.keep("ExtractMeshTerrainPoints_0", PrimaryInput=terrain)    # Extract Mesh Terrain Points
    g.connect(points, g.py, "MeshTerrain")
    g.connect(g.keep("GetActorData_TerrainShaping1"), g.py, "TerrainShaping")
    g.connect(g.keep("Subgraph_3"), g.py, "City")                         # Get City Shape Spline

    # ---- native per-point work between the two Python nodes ----
    hills = g.keep("SpatialNoise_Hills", PrimaryInput=points, NoiseAmplitude=g.p("HillsHeight"))
    flat = g.keep("FlattenProject_AroundCircle", PrimaryInput=hills, SecondaryInput=g.py["FlattenArea"])
    city = g.keep("Subgraph_5", PrimaryInput=flat, SecondaryInput=g.py["CityFlatZone"])
    g.connect(flat, blend, "Hills")
    g.connect(city, blend, "City")

    # ---- the terrain write ----
    write = g.keep("WriteMeshTerrain_0", PrimaryInput=blend["Terrain"])
    g.out(write)
    return g
