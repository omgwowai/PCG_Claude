"""The 18 stages in the Feishu doc's order (ruling R1), and stage 0, the host probe.

Stage modules (sNN_*.py) follow pypcg.stage_api; the slim graph that runs each one is described in
pypcg/graphs/sNN_*.py."""
import importlib

OFFICIAL_DIR = "/CitySamplePCG/Levels/PCG/"

STAGES = [
    (1, "PCG_1_1_Terrain", "s01_terrain", "地形底座"),
    (2, "PCG_1_2_BG_Buildings", "s02_bg_buildings", "远景天际线"),
    (3, "PCG_1_3_BG_Mountains", "s03_bg_mountains", "远景山体"),
    (4, "PCG_2_1_MainTower_Footprint", "s04_main_tower_footprint", "主塔占位"),
    (5, "PCG_2_2_CentralPark_Footprint", "s05_central_park_footprint", "中央公园范围"),
    (6, "PCG_3_1_1_Districts", "s06_districts", "街区骨架"),
    (7, "PCG_3_1_2_Roads", "s07_roads", "道路"),
    (8, "PCG_3_1_3_Highways", "s08_highways", "高速"),
    (9, "PCG_3_1_4_Lots", "s09_lots", "地块"),
    (10, "PCG_3_2_1_Ground", "s10_ground", "地面与人行道"),
    (11, "PCG_3_3_1_Buildings", "s11_buildings", "建筑"),
    (12, "PCG_3_3_2_Rooftops", "s12_rooftops", "屋顶设备"),
    (13, "PCG_3_2_2_LeftOverLots", "s13_leftover_lots", "余地广场与植被"),
    (14, "PCG_3_2_3_Parkings", "s14_parkings", "停车场"),
    (15, "PCG_4_1_MainTower_Visuals", "s15_main_tower_visuals", "主塔视觉"),
    (16, "PCG_4_2_CentralPark_Visuals", "s16_central_park_visuals", "中央公园视觉"),
    (17, "PCG_5_1_CityEdge", "s17_city_edge", "滨水设施"),
    (18, "PCG_5_2_OuterForest", "s18_outer_forest", "外围林地"),
]
PROBE = (0, "PCG_PyProbe", "s00_probe", "探针")

# Which stages read a stage's output through Get_ActorDataByRef (official graphs, 2026-10-15 scan).
DOWNSTREAM = {1: [7, 10, 18], 4: [7, 9, 10, 13, 15], 5: [7, 9, 10, 13, 16, 18], 6: [7, 9, 10, 13],
              7: [8, 9, 10, 13, 16, 18], 8: [9, 13, 18], 9: [10, 11, 13], 11: [12], 13: [14], 14: [16]}


def entry(n):
    if n == PROBE[0]:
        return PROBE
    for s in STAGES:
        if s[0] == n:
            return s
    raise KeyError("no stage %r" % (n,))


def name(n):
    """The graph name, which is also the label of the stage's volume in the demo and town levels."""
    return entry(n)[1]


LABEL = name


def names():
    return [s[1] for s in STAGES]


def official_path(n):
    return OFFICIAL_DIR + name(n)


def spec(n):
    """The stage's Python module (pypcg.stages.sNN_*). Imported, so an edited stage file takes effect."""
    return importlib.import_module("pypcg.stages." + entry(n)[2])
