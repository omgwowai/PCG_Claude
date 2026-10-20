"""Slim graph of stage 18, OuterForest (spec 2.4).

Two Python nodes: `s18_outer_forest` (the footprint, the exclusion areas and the scatter) and
`s18_outer_forest_trees` (everything after the two texture writes, up to the asset assignment).

Scene reads, kept: `GetMeshTerrain_0` (Final, a 3 km query) -> `Subgraph_7 Extract_MeshTerrainPoints` into the
first node's `MeshTerrain` (its points give the footprint), and `GetMeshTerrain_0` itself into the second node's
`MeshTerrain` (the surface the trees are projected onto -- officially through the named reroute `Mesh Terrain
Final`); `Subgraph_6 Get City Boundary` (tag City), `Subgraph_16 Get Central Park Footprint`, `Subgraph_0 Get
Highway Volume`; `Subgraph_4 Get Roads` reaches the first node through the two official nodes that read the
artery width off the road footprint, `FilterDataByTag_0` (tags containing `Polygon`) and
`ExtractAttributeAtIndex_0` (`@data.ArteryWidth`) -- a Python node cannot read a data-domain attribute in this
build (stage 10's reading, kept the same way). `Subgraph_13 Get City Layout Volume` is kept and left unwired,
exactly as the official graph leaves it (it has no consumer there).

Kept native between the two Python nodes (spec 4.3: the texture read is not reproducible in pure Python):

  ForestPoints -> Subgraph_12 Write Tree Scale from Noise Texture (`$scale`, ScaleMin..ScaleMax from the
                  ScaleMin / ScaleMax getters, as officially) -> Subgraph_2 Tree Species From Texture (`index`,
                  1..`CreateConstant_3` (9), also kept) -> s18_outer_forest_trees -> SpawnForest_0

What differs from the official wiring: the named reroute `Mesh Terrain Final` is two direct edges; `Branch_0`
(`UseMegaPlantsTrees`) is inside the second Python node, which reads the parameter from the slim graph's own
getter; `Partitioned` is dropped with `Branch_1`, `Subgraph_17 GridPartition` and `Loop_0` -- `Output A`, the
side every volume here takes, feeds the spawner directly. The official output node is unwired; so is the slim
graph's (no `out()` call): the stage publishes nothing.
"""
from pypcg import dsl
from pypcg.stages import s18_outer_forest as S
from pypcg.stages import s18_outer_forest_trees as T

READS = {"City": "Subgraph_6", "CentralParkFootprint": "Subgraph_16", "Highways": "Subgraph_0"}


def build():
    g = dsl.SlimGraph(S, extra_params=(dsl.official_param(S.STAGE, "ScaleMin"),
                                       dsl.official_param(S.STAGE, "ScaleMax")), more_modules=(T,))
    trees = g.pynodes["s18_outer_forest_trees"]

    # ---- the scene reads ----
    terrain = g.keep("GetMeshTerrain_0")                               # Get MeshTerrain Final
    points = g.keep("Subgraph_7", PrimaryInput=terrain)                # Extract Terrain Points
    g.connect(points, g.py, "MeshTerrain")
    for pin, name in READS.items():
        g.connect(g.keep(name), g.py, pin)
    roads = g.keep("Subgraph_4")                                       # Get Roads
    polygons = g.keep("FilterDataByTag_0", In=roads)                   # Filter Road Polygons
    artery = g.keep("ExtractAttributeAtIndex_0", In=polygons["InsideFilter"])
    g.connect(artery, g.py, "ArteryWidth")
    g.keep("Subgraph_13")                                              # Get City Layout Volume: no user

    # ---- the two native texture writes, then the trees ----
    scale = g.keep("Subgraph_12", PrimaryInput=g.py["ForestPoints"], RemapValueOutLow=g.p("ScaleMin"),
                   RemapValueOutHigh=g.p("ScaleMax"))
    species = g.keep("Subgraph_2", PrimaryInput=scale, RemapValueOutHigh=g.keep("CreateConstant_3"))
    g.connect(species, trees, "ForestPoints")
    g.connect(terrain, trees, "MeshTerrain")
    g.keep("SpawnForest_0", PrimaryInput=trees["Trees"])               # Spawn Outer Forest Trees
    return g
