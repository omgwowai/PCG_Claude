"""Control-spline layout of the ~1.1 x 0.9 km town (cm, world space, Z = 0). No unreal import.

Change the town by editing this file only; test_town_layout.py checks the relations the 18 stages rely
on (arteries cross the city, the highway pair cuts the north-east corner so UnderHighway lots exist,
landmarks keep clear of edges and roads).

The number for the town is this module's, not the demo's: the demo's CityShape is ~9.7 km wide over
terrain that carries the whole CitySample skyline, and the town is what fits between the highway pair
and the park. Everything downstream -- Roads, Lots, Ground, Buildings, LeftOverLots, Parkings,
CityEdge -- derives its geometry from these splines, so a coordinate here is a layout decision, not a
constant to be tuned later.

The parking lot is laid out but never moved or scaled onto the level: ParkingFootprint is the
LeftOverLots volume, and Parkings consumes whatever lots LeftOverLots reserves (Task 25, decision 1).
`parking_rect()` is the *nominal* 70 x 45 m lot the spec asks for; it is reported, not placed.
"""
import math

CITY = [(55000, 0), (42000, 33000), (8000, 45000), (-30000, 40000), (-55000, 10000),
        (-48000, -28000), (-10000, -45000), (35000, -38000)]


def ellipse(cx, cy, rx, ry, n):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


TERRAIN_SHAPING = ellipse(0, 0, 80000, 65000, 16)
ARTERY_A1 = [(-80000, -5000), (-20000, 2000), (25000, -3000), (80000, 4000)]       # east-west
ARTERY_A2 = [(-6000, -70000), (2000, -15000), (-3000, 20000), (5000, 70000)]       # north-south

_HIGHWAY_C = 65000                 # centre line x + y = 65000
_HALF_GAP = 1500 * math.sqrt(2)     # 15 m either side along the normal -> 30 m apart


def _highway(c):
    return [(x, c - x) for x in range(-25000, 90001, 11500)]


HIGHWAY_2 = _highway(_HIGHWAY_C - _HALF_GAP)
HIGHWAY_3 = _highway(_HIGHWAY_C + _HALF_GAP)

MAIN_TOWER = (25000, 15000)
TOWER_HALF = 5500                  # ~110 m footprint (spec D7); 8000 is the 160 m fallback
HIGHRISE = ellipse(MAIN_TOWER[0], MAIN_TOWER[1], 10000, 10000, 12)
LANDMARK_PARK = [(14000 + sx * 3500, 15000 + sy * 3500) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

PARK_CENTER = (-25000, -17000)
PARK_YAW = 30.0
PARK_HALF = (13000, 4500)          # 260 x 90 m


def park(u, v):
    """A point of the park's own frame in world space: u along the long side, v across it."""
    r = math.radians(PARK_YAW)
    return (PARK_CENTER[0] + u * math.cos(r) - v * math.sin(r), PARK_CENTER[1] + u * math.sin(r) + v * math.cos(r))


PARK_RECT = [park(sx * PARK_HALF[0], sy * PARK_HALF[1]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
LAKE = [park(u, v) for u, v in ellipse(6000, 0, 2500, 1500, 12)]
PARK_PATHS = ([park(u, 2000 + 400 * math.sin(u / 4000.0)) for u in range(-12000, 12001, 3000)],
              [park(u, -2000 + 400 * math.cos(u / 4000.0)) for u in range(-12000, 12001, 3000)])
FOREST_EXCLUSION = [park(-7000 + su * 1500, 1500 + sv * 1250) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

PARKING_CENTER = (-36000, 15000)
PARKING_HALF = (3500, 2250)        # 70 x 45 m (nominal: see the module docstring)


def parking_rect():
    cx, cy = PARKING_CENTER
    return [(cx + sx * PARKING_HALF[0], cy + sy * PARKING_HALF[1]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _3d(points):
    return [(float(x), float(y), 0.0) for x, y in points]


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

# The closed ones, for readers that want the set without walking SPLINES.
SPLINE_CLOSED = tuple(n for n, s in SPLINES.items() if s["closed"])

# Control actors the town does not need (labels in the template copy).
DESTROY = ["Artery_3", "HighRise_Zone_2", "Lake_2", "ForestExclusion_2"]

# Volumes whose location defines a landmark. Z is kept; yaw is set when given.
VOLUME_MOVES = {
    "PCG_2_1_MainTower_Footprint": {"xy": MAIN_TOWER},
    "PCG_4_1_MainTower_Visuals": {"xy": MAIN_TOWER},
    "PCG_2_2_CentralPark_Footprint": {"xy": PARK_CENTER, "yaw": PARK_YAW},
}

# The town's stage labels are the stage table's (pypcg.stages.STAGES); bind resolves roles through
# ROLE_LABELS and looks each one up in the town level, so the table is repeated here as data for the
# offline checks (a test keeps the two in step).
STAGE_LABELS = {
    1: "PCG_1_1_Terrain", 2: "PCG_1_2_BG_Buildings", 3: "PCG_1_3_BG_Mountains",
    4: "PCG_2_1_MainTower_Footprint", 5: "PCG_2_2_CentralPark_Footprint",
    6: "PCG_3_1_1_Districts", 7: "PCG_3_1_2_Roads", 8: "PCG_3_1_3_Highways",
    9: "PCG_3_1_4_Lots", 10: "PCG_3_2_1_Ground", 11: "PCG_3_3_1_Buildings",
    12: "PCG_3_3_2_Rooftops", 13: "PCG_3_2_2_LeftOverLots", 14: "PCG_3_2_3_Parkings",
    15: "PCG_4_1_MainTower_Visuals", 16: "PCG_4_2_CentralPark_Visuals",
    17: "PCG_5_1_CityEdge", 18: "PCG_5_2_OuterForest",
}

# The 13 Get_ActorDataByRef roles and the label each resolves to in the town (Task 8's measured labels,
# the same ones the template copy carries). Kept here as data so the tests can check the bindings file
# against the layout without importing the editor-side official profile.
ROLE_LABELS = {
    "Terrain": "PCG_1_1_Terrain", "MainTower": "PCG_2_1_MainTower_Footprint",
    "CentralParkFootprint": "PCG_2_2_CentralPark_Footprint", "Districts": "PCG_3_1_1_Districts",
    "Roads": "PCG_3_1_2_Roads", "Highways": "PCG_3_1_3_Highways", "Lots": "PCG_3_1_4_Lots",
    "Buildings": "PCG_3_3_1_Buildings", "Parkings": "PCG_3_2_3_Parkings",
    "ParkingFootprint": "PCG_3_2_2_LeftOverLots", "LandmarkPark": "MainTowerPark",
    "HighwaySpline2": "HighWay_2", "HighwaySpline3": "HighWay_3",
}

# The actor tags the kept native nodes read, each with the control actors that must carry it after
# `layout`. A tag with no carrier is a silent zero in the stage that reads it (traps.md 1).
TAGS = {
    "City": ["CityShape"],
    "Terrain_shaping_1": ["TerrainShaping"],
    "Arteries": ["Artery_1", "Artery_2"],
    "Highway": ["HighWay_2", "HighWay_3"],
    "HighRise": ["HighRise_Zone_1"],
    "LandmarkPark": ["MainTowerPark"],
    "LAKE": ["Lake_1"],
    "USER_SPLINE": ["ParkPath_1", "ParkPath_2"],
    "FOREST_EXCLUSION": ["ForestExclusion_1"],
}


def city_bbox(margin_cm=0):
    xs, ys = [p[0] for p in CITY], [p[1] for p in CITY]
    return [[min(xs) - margin_cm, min(ys) - margin_cm, -1e9], [max(xs) + margin_cm, max(ys) + margin_cm, 1e9]]


# ---- geometry
def _seg_distance(p, a, b):
    (px, py), (ax, ay), (bx, by) = p[:2], a[:2], b[:2]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def edge_distance(p, polygon):
    return min(_seg_distance(p, polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def polyline_distance(p, polyline):
    return min(_seg_distance(p, polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def inside(p, polygon):
    x, y = p[:2]
    hit = False
    for i in range(len(polygon)):
        (x1, y1), (x2, y2) = polygon[i][:2], polygon[(i + 1) % len(polygon)][:2]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / float(y2 - y1):
            hit = not hit
    return hit


def _cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and (orient(c, d, a) > 0) != (orient(c, d, b) > 0)


def crossings(polyline, shape, closed=True):
    """How many times the open polyline crosses the edges of shape (closed polygon by default)."""
    edges = [(shape[i], shape[(i + 1) % len(shape)]) for i in range(len(shape) if closed else len(shape) - 1)]
    return sum(1 for i in range(len(polyline) - 1) for c, d in edges if _cross(polyline[i], polyline[i + 1], c, d))
