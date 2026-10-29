"""The PyInterior graph /Game/PyPCG/Interior/PCGI_House (spec 2026-10-28 §3.2): the house actor's own spline and transform
-> one Python node -> the native mesh spawner (mesh and slot-0 material by attribute). pyinterior.py build writes it
(pypcg.build.build_slim, 0 diffs)."""
from pypcg import dsl
from pypcg.interior import GRAPH
from pypcg.stages import i01_house
from pypcg.world.graphs import _mesh_spawner


def house():
    g = dsl.SlimGraph(i01_house, name=GRAPH)
    g.connect(g.node("PCGGetSplineSettings", "Get Footprint (the house's own spline)"), g.py, "Footprint")
    g.connect(g.self_point("Get House Actor (Self)"), g.py, "Volume")
    _mesh_spawner(g, g.py["Parts"], "Spawn Walls, Floors, Doors, Windows and Furniture", materials=("Mat0",))
    g.out(g.py["Rooms"], g.py["Summary"])
    return g
