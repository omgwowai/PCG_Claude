"""Slim graph of stage 14, Parkings (spec 2.4).

Two Python nodes: `s14_parkings` (every computation before the two kept grammar nodes) and
`s14_parkings_finish` (every computation after them, before the spawner).

The official graph publishes nothing (its output node has no wired input) and neither does this one: there is
no `out()` call.

Scene reads: `Subgraph_0 Get Parking Lot Footprint` (role ParkingFootprint: the stage-13 volume) into
`s14_parkings`; `Subgraph_1 Get Mesh Terrain (Final)` into `s14_parkings_finish`.

Generation side, kept:

  CentralLines, Border -> Subgraph_53 Assign Concrete Barrier Grammar   -\
  Border               -> Subgraph_54 Assign Chain-Link Fence Grammar    |
  Lines, Tiles, Arrows, ForwardCars, ReverseCars                         |-> s14_parkings_finish (Subgraph_3's
                                                                         |   In Points order: 7, 53, 54, tiles,
                                                                        -/   arrows, forward, reverse cars)
                                                          -> Points -> Subgraph_13 Spawn All Parking Lot Assets

What differs from the official wiring: the named reroutes are plain edges; `Partitioned` is dropped with
`Branch_1`, `Subgraph_12 GridPartition` and `Loop_0` (false on every volume this port runs, so `Output A` --
the spawner -- is the side the official graph takes); the disabled `Subgraph_2 Debug: Outer Parking Lines` is
dropped.
"""
from pypcg import dsl
from pypcg.stages import s14_parkings as S
from pypcg.stages import s14_parkings_finish as F

READS = {"ParkingFootprint": "Subgraph_0"}
TERRAIN = "Subgraph_1"
# Subgraph_3's In Points, in the official order: Subgraph_7 (the line decals), Subgraph_53, Subgraph_54, the
# tiles (NamedRerouteUsage_1), the arrows (_6), the forward (_7) and reverse (_8) cars
FINISH_ORDER = ("Lines", "Subgraph_53", "Subgraph_54", "Tiles", "Arrows", "ForwardCars", "ReverseCars")


def build():
    g = dsl.SlimGraph(S, more_modules=(F,))
    fin = g.pynodes["s14_parkings_finish"]
    k = {name: g.keep(name) for name in list(READS.values()) + [TERRAIN, "Subgraph_53", "Subgraph_54", "Subgraph_13"]}

    # ---- the scene reads ----
    for pin, name in READS.items():
        g.connect(k[name], g.py, pin)
    g.connect(k[TERRAIN], fin, "MeshTerrain")

    # ---- the two grammars (Subgraph_53 reads NamedRerouteUsage_9 then _13) ----
    g.connect([g.py["CentralLines"], g.py["Border"]], k["Subgraph_53"], "PrimaryInput")
    g.connect(g.py["Border"], k["Subgraph_54"], "PrimaryInput")

    # ---- everything after them, then the spawner ----
    g.connect([k[n] if n in k else g.py[n] for n in FINISH_ORDER], fin, "Points")
    g.connect(fin["Points"], k["Subgraph_13"], "PrimaryInput")
    return g
