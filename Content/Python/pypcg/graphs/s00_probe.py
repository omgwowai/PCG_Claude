"""Slim graph of the host probe: the volume itself, the final mesh terrain, the City spline and a read
that finds nothing feed the Python node; every output goes to the graph output."""
from pypcg import dsl
from pypcg.stages import s00_probe as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.self_point(), g.py, "Volume")
    terrain = g.sub("Get_MeshTerrain", "Get Mesh Terrain (Final)",
                    set={"MeshPartitionBoundSize": {"X": 300000, "Y": 300000, "Z": 100000}, "MeshPartitionQueryType": "Final"})
    g.connect(terrain, g.py, "Terrain")
    g.connect(g.actor_by_tag("City", "Get City"), g.py, "Spline")
    g.connect(g.actor_by_tag("PyPCG_NoSuchTag", "Get Nothing"), g.py, "Empty")
    for pin in S.OUTPUTS:
        g.out(g.py[pin])
    return g
