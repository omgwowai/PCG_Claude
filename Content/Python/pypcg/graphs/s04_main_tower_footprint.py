"""Slim graph of stage 4, MainTowerFootprint: the volume's own transform (one point, the same read
`Create_Spline_Shape`'s CoreProcess does internally through `GetActorData_1 GetSinglePoint`) feeds the
Python node; its one output goes to the graph output. No generation nodes."""
from pypcg import dsl
from pypcg.stages import s04_main_tower_footprint as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.self_point(), g.py, "Volume")
    g.out(g.py["Footprint"])
    return g
