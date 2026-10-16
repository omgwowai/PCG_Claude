"""Slim graph of stage 6, Districts (spec 2.4): the City and Arteries actor reads feed the Python node;
its seven outputs go to the graph output, where Roads, Lots, Ground and LeftOverLots read them by tag."""
from pypcg import dsl
from pypcg.stages import s06_districts as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.keep("Subgraph_0"), g.py, "City")          # Get City Shape Spline (actor tag City)
    g.connect(g.keep("Subgraph_1"), g.py, "Arteries")      # Get Arteries (actor tag Arteries)
    for pin in S.OUTPUTS:
        g.out(g.py[pin])
    return g
