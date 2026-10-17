"""Slim graph of stage 5, CentralParkFootprint: the volume's own transform (the read
`Create_Spline_Shape`'s CoreProcess does internally through `GetActorData_1 GetSinglePoint`) feeds the
Python node; its one output goes to the graph output. No generation nodes."""
from pypcg import dsl
from pypcg.stages import s05_central_park_footprint as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.self_point(), g.py, "Volume")
    g.out(g.py["Footprint"])
    return g
