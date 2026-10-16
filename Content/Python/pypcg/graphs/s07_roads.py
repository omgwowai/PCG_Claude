"""Slim graph of stage 7, Roads (spec 2.4) -- the footprint half.

The scene reads the official graph keeps feed the Python node: the Districts actor (whose output is
the whole stage-6 tag set) and the two landmark actors the Landmarks spline is built from. The
Python node publishes `RoadFootprints`.

`ModifiedTerrain` is **not** on this graph's output yet. It is produced by the kept `Subgraph_37
Write Terrain (Intersection Flatten)`, a stateful terrain write that stays an engine node by contract
(Ruling 2), and the point chain that feeds it (`Subgraph_33 Extract_MeshTerrainPoints` -> `Subgraph_36
Transform_Project` -> `BlurElement_2`) is the terrain half. Until that half is ported the output pin
is absent rather than wired to something that is not the official chain: a graph that published a
surface it had not flattened would pass V2's presence check while being wrong.

Kept nodes are named exactly as in the official graph, and `keep()` copies each one's class,
subgraph, overrides, settings and pin defaults verbatim, so the slim graph can be compared node by
node against it.
"""
from pypcg import dsl
from pypcg.stages import s07_roads as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.keep("Subgraph_0"), g.py, "Districts")             # Get Actor Data By Ref: Districts
    g.connect(g.keep("Subgraph_12"), g.py, "MainTower")            # Get Actor Data By Ref: MainTower
    g.connect(g.keep("Subgraph_1"), g.py, "CentralParkFootprint")  # Get Actor Data By Ref: CentralPark
    g.out(g.py["RoadFootprints"])
    return g
