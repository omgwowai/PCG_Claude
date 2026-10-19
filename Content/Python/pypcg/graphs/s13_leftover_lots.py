"""Slim graph of stage 13, LeftOverLots (spec 2.4).

Three Python nodes: `s13_leftover_lots` (the areas, the split, the tiles and the tree points),
`s13_leftover_trees` (the outer-forest trees after the two texture writes) and `s13_leftover_plazas` (the
plaza kit points after the five fitting-asset nodes).

Scene reads into `s13_leftover_lots`: `Subgraph_3 Get Lots` (the stage-9 volume, every tag), `Subgraph_6 Get
Districts`, `Subgraph_11 Get Roads`, `Subgraph_22 Get Highway`, `Subgraph_16 Get Landmark`, `Subgraph_33 Central
Park`, `Subgraph_51 Landmark Small Park` and `Subgraph_15 Get_MeshTerrain` (Final); `s13_leftover_plazas` reads
`Subgraph_22` and `Subgraph_15` too.

Published: the plaza lots the second draw did not keep (`PlazaLots`, the official `Reroute_4` -> output node).

Generation side, kept:

  ReservedPlazaAreas   -> Subgraph_2  Fill Reserved Lots with Medium Plazas         -\
  MediumCourtyardAreas -> Subgraph_23 Fill Medium Courtyards with Large Plazas      |  -> s13_leftover_plazas
  SmallCourtyardAreas  -> Subgraph_31 Fill Small Courtyards with Small Plazas       |     (Subgraph_20's
  UnderHighwayAreas    -> Subgraph_53 Fill Under-Highway Lots with Storage Plazas   |     input order)
  SkirtAreas           -> Subgraph_38 Fill Building skirt With Small Plazas         -/    -> Subgraph_74 Spawn Plaza
  GroundTiles          -> Subgraph_72 Spawn ground tiles
  TreePoints           -> Subgraph_27 / Subgraph_28 (the two texture writes, NATIVE: the texture read is not
                          reproducible in pure Python) -> s13_leftover_trees -> Subgraph_76 Spawn Outer Forest Trees

What differs from the official wiring: the named reroutes are plain edges; `Partitioned` is dropped with its
three branches (`Branch_0/1/2`), `Gather_5`, `Subgraph_77 GridPartition` and `Loop_1` -- `Output A`, the side
every volume here takes, feeds each spawner directly; `Branch_3` and `Branch_4` (the `UseMegaplantsTrees`
switches) are inside the Python nodes, which read the parameter from the slim graph's own getter.
"""
from pypcg import dsl
from pypcg.stages import s13_leftover_lots as S
from pypcg.stages import s13_leftover_plazas as P
from pypcg.stages import s13_leftover_trees as T

READS = {"Lots": "Subgraph_3", "Districts": "Subgraph_6", "Roads": "Subgraph_11", "Highways": "Subgraph_22",
         "MainTower": "Subgraph_16", "CentralParkFootprint": "Subgraph_33", "LandmarkPark": "Subgraph_51",
         "MeshTerrain": "Subgraph_15"}
FITTING = {"ReservedPlazaAreas": "Subgraph_2", "MediumCourtyardAreas": "Subgraph_23",
           "SmallCourtyardAreas": "Subgraph_31", "UnderHighwayAreas": "Subgraph_53", "SkirtAreas": "Subgraph_38"}
# Subgraph_20's In Points, in the official order
PLAZA_ORDER = ("Subgraph_2", "Subgraph_23", "Subgraph_31", "Subgraph_53", "Subgraph_38")


def build():
    g = dsl.SlimGraph(S, more_modules=(T, P))
    trees, plazas = g.pynodes["s13_leftover_trees"], g.pynodes["s13_leftover_plazas"]
    k = {}
    for name in (list(READS.values()) + list(FITTING.values())
                 + ["Subgraph_27", "Subgraph_28", "Subgraph_72", "Subgraph_74", "Subgraph_76"]):
        k[name] = g.keep(name)

    # ---- the scene reads ----
    for pin, name in READS.items():
        g.connect(k[name], g.py, pin)

    # ---- published: the plaza lots the second draw did not keep (Reroute_4) ----
    g.out(g.py["PlazaLots"])

    # ---- the five fitting-asset nodes, then the plaza points' own node ----
    for pin, name in FITTING.items():
        g.connect(g.py[pin], k[name], "PrimaryInput")
    g.connect([k[n] for n in PLAZA_ORDER], plazas, "Plazas")
    g.connect(k["Subgraph_22"], plazas, "Highways")
    g.connect(k["Subgraph_15"], plazas, "MeshTerrain")
    g.connect(plazas["PlazaPoints"], k["Subgraph_74"], "PrimaryInput")

    # ---- ground tiles ----
    g.connect(g.py["GroundTiles"], k["Subgraph_72"], "PrimaryInput")

    # ---- trees: the native texture writes between the two Python nodes ----
    g.connect(g.py["TreePoints"], k["Subgraph_27"], "PrimaryInput")
    g.connect(k["Subgraph_27"], k["Subgraph_28"], "PrimaryInput")
    g.connect(k["Subgraph_28"], trees, "TreePoints")
    g.connect(trees["Trees"], k["Subgraph_76"], "PrimaryInput")
    return g
