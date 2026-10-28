"""PyWorld: the world-building pipeline of "Building Worlds with Houdini" (Ubisoft Paris) as nine PCG graphs with
Python nodes (docs/superpowers/specs/2026-10-22-pyworld-video-pipeline-design.md). No unreal import."""

STAGES = [
    (1, "PCGW_01_Terrain", "w01_terrain", "地形"),
    (2, "PCGW_02_Locations", "w02_locations", "地点"),
    (3, "PCGW_03_River", "w03_river", "河流"),
    (4, "PCGW_04_Roads", "w04_roads", "道路"),
    (5, "PCGW_05_Bridges", "w05_bridges", "桥"),
    (6, "PCGW_06_Settlements", "w06_settlements", "聚落"),
    (7, "PCGW_07_Vegetation", "w07_vegetation", "植被与岩石"),
    (8, "PCGW_08_Props", "w08_props", "沿路道具"),
    (9, "PCGW_09_Surface", "w09_surface", "地表材质"),
]
STAGE_BASE = 100                       # a world module's STAGE is 100 + n: apart from the city's 1..18
ASSET_DIR = "/Game/PyPCG/World/"
LEVEL = "/Game/PyPCG/L_PyWorld"
TEMPLATE = "/Game/PyPCG/L_PyCity"
VERTEX_CM = 585.9375                   # the mesh terrain's vertex spacing (docs/pypcg/stages/s01.md 0)
QUERY_BOX = {"X": 300000, "Y": 300000, "Z": 300000}
WORLD_HALF_CM = 100000.0               # the 2 km box the roads, settlements and props live in
SEA_Z = -600.0                         # the base terrain's height, under the template's ocean plane (-500)
ROAD_INNER = 600.0                     # a road corridor is flat to half width + this ...
ROAD_BLEND = 1000.0                    # ... and eases back to the ground over this
# stage -> (query type, query sub-priority, write sub-priority) of its mesh terrain read and write
TERRAIN = {1: ("Base", 0, 1), 3: ("Intermediate", 2, 3), 4: ("Intermediate", 4, 5), 6: ("Intermediate", 6, 7),
           9: ("Intermediate", 8, 9)}
CHANNELS = ("Grass", "Rock", "ForestFloor", "Dirt", "Mud", "Gravel")      # MPD_Basic's material channels
MPD_BASIC = "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic"
# MPD_Basic with Megascans surfaces on its 6 channels (pyworld_terrain_material.py builds it; layout uses it when present)
MPD_WORLD = "/Game/PyPCG/World/MPD_PyWorld"


def _p(pkg):
    return "%s.%s" % (pkg, pkg.rsplit("/", 1)[1])


_MP = "/CitySamplePCG/Megaplants/Tree_%s/Tree_%s_01/SM_%s_01_%s"
MESH = {
    "Cube": _p("/Engine/BasicShapes/Cube"), "Cylinder": _p("/Engine/BasicShapes/Cylinder"),
    "Cone": _p("/Engine/BasicShapes/Cone"), "Plane": _p("/Engine/BasicShapes/Plane"),
    "LaneCar": _p("/PCGPrimitives/Meshes/SM_Lane_Car_400_500"),            # X -250..250, Y -200..200, Z 0..20
    "Divider": _p("/PCGPrimitives/Meshes/SM_Lane_Divider_15_500"),         # X -250..250, Y -7.5..7.5
    "Path": _p("/PCGPrimitives/Meshes/SM_Lane_Path_300_160"),              # X -80..80, Y -150..150
    "Tile": _p("/PCGPrimitives/Meshes/SM_Square_150_150"),                 # X, Y -75..75, Z 0..20
    "Bench": _p("/PCGPrimitives/Meshes/SM_park_bench_N01"),                # X -114..114 (long), Z 0..95
    "Rail": _p("/Game/Megascans/3D_Assets/Modular_Rail_Guard_4m_00/Modular_Rail_Guard_4m_LOD0_uh1kbcxga"),  # X 0..420
    "Lamp": _p("/Game/Prop/Kit_StreetLamp_A/Mesh/SM_StreetLamp_A_Pole_Small"),  # Z 0..420, arm towards +X
    "MossyRock": _p("/Game/Megascans/3D_Assets/Mossy_Rock_ulldfii/S_Mossy_Rock_ulldfii_lod3_Var1"),
    "Boulder": _p("/PCGBiomeSample/Meshes/PCG_Boulder_01"),
    "Pine": _p("/PCGBiomeSample/Meshes/PCG_Pine_01"), "Spruce": _p("/PCGBiomeSample/Meshes/PCG_Spruce_01"),
    "YoungTree": _p("/PCGBiomeSample/Meshes/PCG_Tree_01"),
}
for _v in "ABCD":
    MESH["Alder" + _v] = _p(_MP % ("Black_Alder", "Black_Alder", "Black_Alder", _v))
    MESH["Hazel" + _v] = _p(_MP % ("Common_Hazel", "Common_Hazel", "Common_Hazel", _v))
    MESH["Beech" + _v] = _p(_MP % ("European_Beech", "European_Beech", "European_Beech", _v))
    MESH["Aspen" + _v] = _p(_MP % ("European_Aspen", "European_Aspen", "European_Aspen", _v))
    MESH["Maple" + _v] = _p("/CitySamplePCG/Megaplants/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/"
                            "SM_Norway_Maple_Forest_01_" + _v)
for _v in "abcdefgh":
    MESH["Birch" + _v] = _p("/Game/Prop/Kit_Tree_Birch/Mesh/SM_Tree_Birch_" + _v)
for _v in "ABDEFG":
    MESH["Grass" + _v] = _p("/CitySamplePCG/Megascans/Plants/Wild_Grass/Medium/StaticMeshes/SM_Grass_Var" + _v)
WATER_MATERIAL = "/Game/Prop/kit_ocean/Material/MI_ocean.MI_ocean"


def entry(n):
    for s in STAGES:
        if s[0] == n:
            return s
    raise KeyError("no world stage %r" % (n,))


def name(n):
    return entry(n)[1]


def module_name(n):
    return entry(n)[2]


def asset(n):
    return ASSET_DIR + name(n)


def volume_tag(n):
    return "PyWorld_W%02d" % n


def stage_number(module):
    return int(module.STAGE) - STAGE_BASE
