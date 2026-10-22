"""Slim graph of stage 12, Rooftops (spec 2.4).

Two Python nodes: `s12_rooftops` (the class / size / height split and the two offsets, before the four kept
fitting-asset nodes) and `s12_rooftops_assemblies` (the WFC points less the small assemblies' points, after two of
them, before the kept spawner).

The official graph publishes nothing (its output node has no wired input) and neither does this one: there is no
`out()` call.

Scene read: `Subgraph_0 Get Building Rooftop Polygons` (role Buildings: the stage-11 volume) into `s12_rooftops`.

Generation side, kept:

  SmallAssemblyAreas -> Subgraph_2  Place Small Rooftop Assemblies                 --+ WfcPoints / SmallPoints
  WfcAreas           -> Subgraph_7  Place WFC Rooftop Assemblies (Medium & Large) --+-> s12_rooftops_assemblies
  SkyscraperAreas    -> Subgraph_3  Place Skyscraper Rooftop Assemblies
  VentAreas          -> Subgraph_11 Place AC Vents & Roof Houses (Unfiltered)
  s12_rooftops_assemblies, Subgraph_11, Subgraph_3, Subgraph_2 (Branch_1's In order)
                     -> Subgraph_13 Spawn All Rooftop Assemblies

What differs from the official wiring: `Reroute_0` is a plain edge; `Partitioned` is dropped with `Branch_1`,
`GetGraphParameter_3` and `Loop_0` (false on every volume this port runs, so `Output A` -- the spawner -- is the side
the official graph takes).
"""
from pypcg import dsl
from pypcg.stages import s12_rooftops as S
from pypcg.stages import s12_rooftops_assemblies as A

READS = {"Rooftops": "Subgraph_0"}
FITTING = {"SmallAssemblyAreas": "Subgraph_2", "WfcAreas": "Subgraph_7", "SkyscraperAreas": "Subgraph_3",
           "VentAreas": "Subgraph_11"}
SPAWN = "Subgraph_13"
# Branch_1's In, in the official order: Subgraph_12 (the difference: s12_rooftops_assemblies), 11, 3, 2
SPAWN_ORDER = ("Points", "Subgraph_11", "Subgraph_3", "Subgraph_2")


def build():
    g = dsl.SlimGraph(S, more_modules=(A,))
    asm = g.pynodes["s12_rooftops_assemblies"]
    k = {name: g.keep(name) for name in list(READS.values()) + list(FITTING.values()) + [SPAWN]}

    # ---- the scene read ----
    for pin, name in READS.items():
        g.connect(k[name], g.py, pin)

    # ---- the four fitting-asset nodes ----
    for pin, name in FITTING.items():
        g.connect(g.py[pin], k[name], "PrimaryInput")

    # ---- Subgraph_12: the WFC points (Primary) less the small assemblies' points (Secondary) ----
    g.connect(k["Subgraph_7"], asm, "WfcPoints")
    g.connect(k["Subgraph_2"], asm, "SmallPoints")

    # ---- the spawner ----
    g.connect([asm["Points"] if n == "Points" else k[n] for n in SPAWN_ORDER], k[SPAWN], "PrimaryInput")
    return g
