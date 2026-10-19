"""Slim graph of stage 17, CityEdge (spec 2.4).

The scene read the official graph keeps -- `Subgraph_9 Get_MeshTerrain` (Final, a 3 km x 3 km x 1 km
query) into `Subgraph_10 Extract_MeshTerrainPoints` -- feeds the Python node's `MeshTerrain` pin. The
Python node does everything from the sea-level filter to the asset assignment and hands its `Docks`
to the kept `Subgraph_0 Spawn Pier & Warehouse Assemblies` and to the graph output.

What differs from the official graph's own wiring:

  - `Branch_0` and the partition machinery behind it (`GetGraphParameter_0/1`, `Subgraph_1
    GridPartition`, `Loop_1 LoopSpawnActorPerData`) are dropped by the contract; `Partitioned` is false
    on every volume this port runs, so `Branch_0`'s `Output A` -- the spawner -- is the side the official
    graph takes, and the slim graph wires the Python output straight to it.
  - The official output node is unwired; the slim graph publishes `Docks` (the contract's output),
    which nothing downstream reads (`DOWNSTREAM` has no entry for stage 17).
"""
from pypcg import dsl
from pypcg.stages import s17_city_edge as S


def build():
    g = dsl.SlimGraph(S)
    terrain = g.keep("Subgraph_9")                         # Get Mesh Terrain (Final)
    points = g.keep("Subgraph_10", PrimaryInput=terrain)   # Extract Terrain Points
    g.connect(points, g.py, "MeshTerrain")
    spawn = g.keep("Subgraph_0")                           # Spawn Pier & Warehouse Assemblies
    g.connect(g.py["Docks"], spawn, "PrimaryInput")
    g.out(g.py["Docks"])
    return g
