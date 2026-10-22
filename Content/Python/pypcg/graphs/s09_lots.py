"""Slim graph of stage 9, Lots (spec 2.4).

The seven scene reads the official graph makes feed the Python node: the City outline (actor tag
City), the Districts, Roads, Landmark, Central Park, Landmark Small Park and Highway volumes / actors.
The Roads read keeps its two official tag filters: `Subgraph_60 Filter Road Footprints` feeds the
Python node, and `Subgraph_61 Filter Modified Terrain` the projector of the grammar chain, so the
terrain surface never enters Python (it could not be recorded for V1, trap 60).

The generation side stays native (Ruling 2): `Subgraph_58 Assign Road Grammar To Grid Splines` reads
the Python node's `GridSplines`, and its points go through the official `Subgraph_76` lift (+23 cm),
`Subgraph_62` projection onto the road-modified terrain and `Subgraph_63 Spawn Road Grammar Assets`.

What differs from the official wiring:

  - `Subgraph_76 Transform_Offset` and `Subgraph_62 Custom_Projector_with_rotation_fix` are counted
    as computation by the brief, but they only move the grammar node's own points onto the terrain
    for the spawner; porting them would need a second Python node with a terrain input after the
    grammar node. They stay native, between two kept generation nodes, exactly as wired officially.
  - `Branch_2` (the `Partitioned` switch) is dropped with `Subgraph_11 GridPartition` and
    `Loop_0`: `Subgraph_62` feeds `Subgraph_63` directly, which is the `Output A` side every
    volume here takes.
  - `Subgraph_58.Footprints` is not read: the Python node carves the same 10 m bands itself
    (`s09_lots.grammar_bands`), so the large lots do not need a second Python node after the
    grammar node.
  - The eleven tag writers are Python: each output item carries its contract tag.
"""
from pypcg import dsl
from pypcg.stages import s09_lots as S


def build():
    g = dsl.SlimGraph(S)
    _n = {}
    for name in ("Subgraph_10", "Subgraph_12", "Subgraph_15", "Subgraph_60", "Subgraph_61", "Subgraph_19",
                 "Subgraph_1", "Subgraph_23", "Subgraph_71", "Subgraph_58", "Subgraph_76", "Subgraph_62",
                 "Subgraph_63"):
        _n[name] = g.keep(name)

    # ---- the scene reads ----
    g.connect(_n["Subgraph_10"], g.py, "City")                  # Get City Shape (actor tag City)
    g.connect(_n["Subgraph_12"], g.py, "Districts")             # Get Districts
    g.connect(_n["Subgraph_15"], _n["Subgraph_60"], "PrimaryInput")
    g.connect(_n["Subgraph_60"]["Selected"], g.py, "RoadFootprints")
    g.connect(_n["Subgraph_19"], g.py, "MainTower")             # Get Landmark
    g.connect(_n["Subgraph_1"], g.py, "CentralParkFootprint")   # Get Central_Park
    g.connect(_n["Subgraph_23"], g.py, "LandmarkPark")          # Landmark Small Park
    g.connect(_n["Subgraph_71"], g.py, "Highway")               # Get Highway

    # ---- the contract outputs: every Python pin but the grid lines ----
    g.out(*[g.py[pin] for pin in S.OUTPUTS if pin not in S.INTERNAL])

    # ---- the kept grammar chain over the large lots' inner grid ----
    g.connect(g.py["GridSplines"], _n["Subgraph_58"], "PrimaryInput")
    g.connect(_n["Subgraph_58"]["Points"], _n["Subgraph_76"], "PrimaryInput")
    g.connect(_n["Subgraph_76"]["Out"], _n["Subgraph_62"], "In Points")
    g.connect(_n["Subgraph_15"], _n["Subgraph_61"], "PrimaryInput")
    g.connect(_n["Subgraph_61"]["Selected"], _n["Subgraph_62"], "Surface")
    g.connect(_n["Subgraph_62"]["Out"], _n["Subgraph_63"], "PrimaryInput")
    return g
