"""Control layout of the small area (~560 x 440 m) that /Game/PyPCG/L_PyCitySmall runs PCG_PyCity on (cm, world
space, Z = 0). No unreal import; Tools/pypcg/tests/test_small_layout.py checks the relations the stages rely on.

The same control actors as the town (pypcg.profiles.town_layout), half the size: a city outline crossed by two
arteries into four quarters, a highway pair cutting the north-east corner, the main tower and its high-rise
zone and small park in the north-east quarter, the central park with its lake, paths and forest exclusion in
the south-west quarter. Road widths, lot sizes and building heights stay real-scale parameters, so a smaller
outline means fewer, not smaller, blocks; the district class thresholds are scaled with the area
(pypcg.profiles.small)."""
import math

from pypcg.profiles.town_layout import (ROLE_LABELS, STAGE_LABELS, _3d, crossings, edge_distance, ellipse,  # noqa: F401
                                        inside, polyline_distance)

CITY = [(28000, 0), (21000, 17000), (4000, 22000), (-15000, 20000), (-28000, 5000),
        (-25000, -14000), (-5000, -22000), (18000, -19000)]

TERRAIN_SHAPING = ellipse(0, 0, 42000, 34000, 16)
ARTERY_A1 = [(-42000, -2500), (-10000, 1000), (12000, -1500), (42000, 2000)]       # east-west
ARTERY_A2 = [(-3000, -36000), (1000, -8000), (-1500, 10000), (2500, 36000)]        # north-south

_HIGHWAY_C = 37000                 # centre line x + y = 37000: cuts the north-east corner (21000, 17000)
_HALF_GAP = 1500 * math.sqrt(2)     # 15 m either side along the normal -> 30 m apart, as in the town


def _highway(c):
    return [(x, c - x) for x in range(-12000, 50001, 6200)]


HIGHWAY_2 = _highway(_HIGHWAY_C - _HALF_GAP)
HIGHWAY_3 = _highway(_HIGHWAY_C + _HALF_GAP)

MAIN_TOWER = (11000, 8500)
TOWER_HALF = 5500                  # 110 m footprint, the town's (S04_RectWidth / RectLength 11000); 80 m builds no upper levels
HIGHRISE = ellipse(MAIN_TOWER[0], MAIN_TOWER[1], 10000, 10000, 12)
LANDMARK_PARK = [(11000 + sx * 2500, -9500 + sy * 2500) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

PARK_CENTER = (-13000, -9500)
PARK_YAW = 30.0
PARK_HALF = (6000, 2500)           # 120 x 50 m (S05_RectWidth / RectLength 12000 / 5000)


def park(u, v):
    """A point of the park's own frame in world space: u along the long side, v across it."""
    r = math.radians(PARK_YAW)
    return (PARK_CENTER[0] + u * math.cos(r) - v * math.sin(r), PARK_CENTER[1] + u * math.sin(r) + v * math.cos(r))


PARK_RECT = [park(sx * PARK_HALF[0], sy * PARK_HALF[1]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
LAKE = [park(u, v) for u, v in ellipse(2500, 0, 1500, 900, 12)]
PARK_PATHS = ([park(u, 1100 + 200 * math.sin(u / 2000.0)) for u in range(-5500, 5501, 1375)],
              [park(u, -1100 + 200 * math.cos(u / 2000.0)) for u in range(-5500, 5501, 1375)])
FOREST_EXCLUSION = [park(-3200 + su * 900, 800 + sv * 700) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

SPLINES = {
    "CityShape": {"points": _3d(CITY), "closed": True, "linear": False},
    "TerrainShaping": {"points": _3d(TERRAIN_SHAPING), "closed": True, "linear": False},
    "Artery_1": {"points": _3d(ARTERY_A1), "closed": False, "linear": False},
    "Artery_2": {"points": _3d(ARTERY_A2), "closed": False, "linear": False},
    "HighWay_2": {"points": _3d(HIGHWAY_2), "closed": False, "linear": False},
    "HighWay_3": {"points": _3d(HIGHWAY_3), "closed": False, "linear": False},
    "HighRise_Zone_1": {"points": _3d(HIGHRISE), "closed": True, "linear": False},
    "MainTowerPark": {"points": _3d(LANDMARK_PARK), "closed": True, "linear": True},
    "Lake_1": {"points": _3d(LAKE), "closed": True, "linear": False},
    "ParkPath_1": {"points": _3d(PARK_PATHS[0]), "closed": False, "linear": False},
    "ParkPath_2": {"points": _3d(PARK_PATHS[1]), "closed": False, "linear": False},
    "ForestExclusion_1": {"points": _3d(FOREST_EXCLUSION), "closed": True, "linear": True},
}
SPLINE_CLOSED = tuple(n for n, s in SPLINES.items() if s["closed"])

# The footprint control actors (pypcg.combined.CONTROL_TAGS): location, and yaw when given. Z is kept.
CONTROL_MOVES = {
    "PCG_2_1_MainTower_Footprint": {"xy": MAIN_TOWER},
    "PCG_2_2_CentralPark_Footprint": {"xy": PARK_CENTER, "yaw": PARK_YAW},
}

TAGS = {
    "City": ["CityShape"], "Terrain_shaping_1": ["TerrainShaping"], "Arteries": ["Artery_1", "Artery_2"],
    "Highway": ["HighWay_2", "HighWay_3"], "HighRise": ["HighRise_Zone_1"], "LandmarkPark": ["MainTowerPark"],
    "LAKE": ["Lake_1"], "USER_SPLINE": ["ParkPath_1", "ParkPath_2"], "FOREST_EXCLUSION": ["ForestExclusion_1"],
    "PyCity_MainTowerFootprint": ["PCG_2_1_MainTower_Footprint"],
    "PyCity_CentralParkFootprint": ["PCG_2_2_CentralPark_Footprint"],
}


def tower_rect():
    (cx, cy), h = MAIN_TOWER, TOWER_HALF
    return [(cx + sx * h, cy + sy * h) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def city_bbox(margin_cm=0):
    xs, ys = [p[0] for p in CITY], [p[1] for p in CITY]
    return [[min(xs) - margin_cm, min(ys) - margin_cm, -1e9], [max(xs) + margin_cm, max(ys) + margin_cm, 1e9]]


def area_m2(polygon):
    return abs(sum(polygon[i][0] * polygon[(i + 1) % len(polygon)][1] - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
                   for i in range(len(polygon)))) / 2.0 / 1e4
