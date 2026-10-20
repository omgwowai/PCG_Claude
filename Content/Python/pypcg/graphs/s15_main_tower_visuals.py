"""Slim graph of stage 15, MainTowerVisuals (spec 2.4).

Six Python nodes, because the computation interleaves with the native building nodes (a contract of one
tower's rooftops is the next tower's footprint):

  s15_main_tower_visuals  everything upstream of the first building node: the rings, the arm sectors, the
                          hexagons, the tree ring (assign + projector + attribute sets) and the plaza tiles
  s15_tower_level1 .. 3   the contracts between the stacked towers, the courtyard, the assembly filter
  s15_tower_top           the antenna point on the skyscraper's rooftop
  s15_tower_sidewalk      the sidewalk grammars' points onto the terrain

The official graph publishes nothing (its output node has no wired input) and neither does this one: there is
no `out()` call.

Scene reads (kept): `Subgraph_35 Get Hero Tower PCG Volume` (role MainTower: the stage-4 footprint),
`Subgraph_26 Get Mesh Terrain (Final)`, `Subgraph_0 LoadCitySampleData` (one, shared by the 17 building nodes,
as `NamedRerouteDeclaration_2` shares it officially). Added: the volume's own transform (`self_point`), the
frame the official arm chain's `Transform_Offset` nodes turn about (s15.md section 5).

Generation side, kept (all 30, official settings):

  InnerRing  -> AssignBuilding (CHC 50 m)               Hexagons -> Subgraph_3 (CHA 25 m) -> Subgraph_4 mesh
  Sector90   -> Subgraph_40 -> 46 -> 48 -> 50 (CHJ 90 m) Sector80 -> 51 -> 53 -> 55 -> 57    Sector70 -> 58 -> 60 -> 62 -> 64
             (each arrow through s15_tower_level1 / 2 / 3, a 1.5 m contract of the rooftops)
  AssignBuilding rooftops -> level1 OuterChj -> Subgraph_6 -> level2 Chj2 -> Subgraph_8 -> level3 Skyscraper
             -> Subgraph_66 -> s15_tower_top -> Subgraph_24 Spawn_Antenna
  level3 Assemblies, Subgraph_66 rooftops -> Subgraph_21 Place Rooftop Assemblies
  Subgraph_50 / 57 / 64 rooftops -> Subgraph_25 Place AC Vents on Arm Rooftops
  level1 Courtyard -> Subgraph_12 / Subgraph_13 grammars -> s15_tower_sidewalk -> Subgraph_32 Spawn Sidewalk
  level1 CourtyardLifted -> Subgraph_14 Courtyard Ground Mesh, Subgraph_41 Place AC Vents
  all 15 tower rooftops (Subgraph_1's official order) -> Subgraph_1 All Building Rooftop Geo
  TreeBases -> Subgraph_16    Trees -> SpawnTrees    PlazaTiles -> SpawnPlaza

What differs from the official wiring: the named reroutes and `Reroute_0/1/2` are plain edges; `Branch_0`
(`UseMegaplantsTrees`) and both `Assign_Assets` calls are inside the main Python node, which reads the parameter
from the slim graph's own getter.
"""
from pypcg import dsl
from pypcg.stages import s15_main_tower_visuals as S
from pypcg.stages import s15_tower_level1 as L1
from pypcg.stages import s15_tower_level2 as L2
from pypcg.stages import s15_tower_level3 as L3
from pypcg.stages import s15_tower_sidewalk as W
from pypcg.stages import s15_tower_top as T

READS = {"Volume": "Subgraph_35", "MeshTerrain": "Subgraph_26"}
CITY_DATA = "Subgraph_0"
ROOFS = "Rooftops Footprints"
# the four towers of each arm, bottom to top
ARMS = {"Arm90": ("Subgraph_40", "Subgraph_46", "Subgraph_48", "Subgraph_50"),
        "Arm80": ("Subgraph_51", "Subgraph_53", "Subgraph_55", "Subgraph_57"),
        "Arm70": ("Subgraph_58", "Subgraph_60", "Subgraph_62", "Subgraph_64")}
SECTOR = {"Arm90": "Sector90", "Arm80": "Sector80", "Arm70": "Sector70"}
BUILDINGS = ("AssignBuilding", "Subgraph_3", "Subgraph_6", "Subgraph_8", "Subgraph_66") + tuple(
    n for chain in ARMS.values() for n in chain)
MESHES = ("Subgraph_1", "Subgraph_4", "Subgraph_14")
SPAWNS = ("SpawnPlaza", "SpawnTrees", "Subgraph_16", "Subgraph_24", "Subgraph_32")
GRAMMARS = ("Subgraph_12", "Subgraph_13")
FITTING = ("Subgraph_21", "Subgraph_25", "Subgraph_41")
# Subgraph_1's PrimaryInput, in the official order
ROOF_MESH_ORDER = ("Subgraph_66", "Subgraph_8", "Subgraph_6", "AssignBuilding", "Subgraph_50", "Subgraph_57",
                   "Subgraph_64", "Subgraph_40", "Subgraph_51", "Subgraph_58", "Subgraph_60", "Subgraph_62",
                   "Subgraph_55", "Subgraph_48", "Subgraph_46")


def build():
    g = dsl.SlimGraph(S, more_modules=(L1, L2, L3, T, W))
    lv = {1: g.pynodes["s15_tower_level1"], 2: g.pynodes["s15_tower_level2"], 3: g.pynodes["s15_tower_level3"]}
    top, walk = g.pynodes["s15_tower_top"], g.pynodes["s15_tower_sidewalk"]
    k = {name: g.keep(name) for name in (list(READS.values()) + [CITY_DATA] + list(BUILDINGS) + list(MESHES)
                                         + list(SPAWNS) + list(GRAMMARS) + list(FITTING))}

    # ---- the scene reads ----
    for pin, name in READS.items():
        g.connect(k[name], g.py, pin)
    g.connect(g.self_point(), g.py, "Self")
    g.connect(k[READS["MeshTerrain"]], walk, "MeshTerrain")
    for name in BUILDINGS:
        g.connect(k[CITY_DATA], k[name], "CitySample data")

    # ---- the main node's footprints, trees and tiles ----
    g.connect(g.py["InnerRing"], k["AssignBuilding"], "BuildingsFootprints")
    g.connect(g.py["Hexagons"], k["Subgraph_3"], "BuildingsFootprints")
    for arm, chain in ARMS.items():
        g.connect(g.py[SECTOR[arm]], k[chain[0]], "BuildingsFootprints")
    g.connect(g.py["TreeBases"], k["Subgraph_16"], "PrimaryInput")
    g.connect(g.py["Trees"], k["SpawnTrees"], "PrimaryInput")
    g.connect(g.py["PlazaTiles"], k["SpawnPlaza"], "PrimaryInput")

    # ---- level 1: the CHC rooftops, the hexagons, each arm's first rooftop ----
    g.connect(k["AssignBuilding"][ROOFS], lv[1], "ChcRoofs")
    g.connect(g.py["Hexagons"], lv[1], "Hexagons")
    g.connect(lv[1]["OuterChj"], k["Subgraph_6"], "BuildingsFootprints")
    for name in GRAMMARS:
        g.connect(lv[1]["Courtyard"], k[name], "PrimaryInput")
    g.connect(lv[1]["CourtyardLifted"], k["Subgraph_14"], "PrimaryInput")
    g.connect(lv[1]["CourtyardLifted"], k["Subgraph_41"], "PrimaryInput")

    # ---- level 2 and 3: the CHJ ring up to the skyscraper ----
    g.connect(k["Subgraph_6"][ROOFS], lv[2], "Chj1Roofs")
    g.connect(lv[2]["Chj2"], k["Subgraph_8"], "BuildingsFootprints")
    g.connect(k["Subgraph_8"][ROOFS], lv[3], "Chj2Roofs")
    g.connect(lv[3]["Skyscraper"], k["Subgraph_66"], "BuildingsFootprints")

    # ---- the arms, one level per stacked tower ----
    for arm, chain in ARMS.items():
        for level in (1, 2, 3):
            g.connect(k[chain[level - 1]][ROOFS], lv[level], arm + "Roofs")
            g.connect(lv[level][arm], k[chain[level]], "BuildingsFootprints")

    # ---- the rooftop dressing ----
    g.connect([lv[3]["Assemblies"], k["Subgraph_66"][ROOFS]], k["Subgraph_21"], "PrimaryInput")
    g.connect([k[ARMS[a][3]][ROOFS] for a in ("Arm90", "Arm80", "Arm70")], k["Subgraph_25"], "PrimaryInput")
    g.connect(k["Subgraph_66"][ROOFS], top, "SkyscraperRoofs")
    g.connect(top["Antenna"], k["Subgraph_24"], "PrimaryInput")
    g.connect([k[n][ROOFS] for n in ROOF_MESH_ORDER], k["Subgraph_1"], "PrimaryInput")
    g.connect(k["Subgraph_3"][ROOFS], k["Subgraph_4"], "PrimaryInput")

    # ---- the sidewalk: Subgraph_31 reads Subgraph_13's points, then Subgraph_12's ----
    g.connect([k["Subgraph_13"]["Points"], k["Subgraph_12"]["Points"]], walk, "SidewalkPoints")
    g.connect(walk["Points"], k["Subgraph_32"], "PrimaryInput")
    return g
