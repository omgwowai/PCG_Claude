"""The valley's control layout: what `pyworld.py layout` writes into L_PyWorld as level actors (spec 2.2).
x, y, radius in cm; the valley axis's control points carry the floor height in z."""
import math

TAG_VALLEY = "PyWorld_Valley"
TAG_LOCATION = "PyWorld_Location"
TAG_RIVER_END = "PyWorld_RiverEnd"
TAG_EXIT = "PyWorld_RoadExit"

FLOOR = [(-150000.0, -800.0), (-120000.0, 0.0), (-100000.0, 600.0), (0.0, 2500.0), (100000.0, 6000.0),
         (150000.0, 12000.0)]                        # (y, floor z): the valley opens to the sea in the south
AXIS_AMPLITUDE = 8000.0
AXIS_WAVELENGTH = 60000.0

LOCATIONS = [("Town", 14000.0, -30000.0, 22000.0), ("VillageNorth", -15000.0, 42000.0, 14000.0),
             ("VillageEast", 22000.0, 78000.0, 12000.0), ("HamletSouth", -18000.0, -72000.0, 7000.0),
             ("HamletWest", -32000.0, 8000.0, 7000.0)]
RIVER_ENDS = [("RiverSource", -2000.0, 99000.0), ("RiverOutlet", -8000.0, -135000.0)]
ROAD_EXITS = [("ExitSouth", 8000.0, -99000.0), ("ExitNorth", 25000.0, 99000.0)]


def floor_z(y):
    if y <= FLOOR[0][0]:
        return FLOOR[0][1]
    for (y0, z0), (y1, z1) in zip(FLOOR, FLOOR[1:]):
        if y <= y1:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return FLOOR[-1][1]


def axis_x(y):
    return AXIS_AMPLITUDE * math.sin(y / AXIS_WAVELENGTH)


def valley_points(step=12500.0):
    n = int(round(300000.0 / step))
    return [(axis_x(-150000.0 + q * step), -150000.0 + q * step, floor_z(-150000.0 + q * step)) for q in range(n + 1)]
