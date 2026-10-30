"""The PyInterior demo street (spec 2026-10-28 §6.2): named footprints and the houses of /Game/PyPCG/L_PyInterior.

Footprints are in the house's local frame (cm): x along the front, y into the house, the front door side at y = 0 (the side
the house actor faces). Houses stand on both sides of a street along world X and face it; the last one is turned 30
degrees. `SHAPES` also serves pyinterior.py's `shape` phase (the "change the outline -> the layout follows" test)."""

SHAPES = {
    "studio": [(0, 0), (600, 0), (600, 500), (0, 500)],
    "onebed": [(0, 0), (800, 0), (800, 650), (0, 650)],
    "twobed": [(0, 0), (1050, 0), (1050, 800), (0, 800)],
    "threebed": [(0, 0), (1300, 0), (1300, 900), (0, 900)],
    "fourbed": [(0, 0), (1600, 0), (1600, 1100), (0, 1100)],
    "lshape": [(0, 0), (1400, 0), (1400, 600), (800, 600), (800, 1100), (0, 1100)],
    "tshape": [(0, 0), (1600, 0), (1600, 600), (1100, 600), (1100, 1100), (500, 1100), (500, 600), (0, 600)],
    "ushape": [(0, 0), (1600, 0), (1600, 1000), (1100, 1000), (1100, 550), (500, 550), (500, 1000), (0, 1000)],
}

FRONT = 1200.0          # cm from the street's centre line to a house front
GAP = 500.0             # between neighbouring houses

# (name, shape, side "N" | "S" | "R", style, seed); N faces -Y (yaw -90), S faces +Y (yaw 90), R is turned 30 degrees
STREET = [
    ("House_01_Studio", "studio", "N", "Scandi", 1),
    ("House_02_OneBed", "onebed", "N", "Warm", 2),
    ("House_03_TwoBed", "twobed", "N", "Modern", 3),
    ("House_04_ThreeBed", "threebed", "N", "Scandi", 4),
    ("House_05_LShape", "lshape", "S", "Warm", 5),
    ("House_06_TShape", "tshape", "S", "Modern", 6),
    ("House_07_UShape", "ushape", "S", "Scandi", 7),
    ("House_08_FourBed", "fourbed", "R", "Warm", 8),
]


def width(shape):
    return max(p[0] for p in SHAPES[shape]) - min(p[0] for p in SHAPES[shape])


def _rect(w, h, x0=0.0, y0=0.0):
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


# the multi-storey houses (spec 2026-10-29 §10.1): (name, [local outline per floor, None = copy the floor below], Floors,
# StairType, style, seed); floor k's spline stands k x 300 cm above the house actor
STOREYS = [
    ("House_11_TwoStorey", [_rect(1000, 800), _rect(1000, 800)], 0, "Auto", "Scandi", 11),
    ("House_12_FrontTerrace", [_rect(1000, 900), _rect(1000, 600, 0, 300)], 0, "Auto", "Warm", 12),
    ("House_13_LTerrace", [SHAPES["lshape"], _rect(800, 1100)], 0, "Auto", "Modern", 13),
    ("House_14_Townhouse", [_rect(550, 1100), _rect(550, 1100), _rect(550, 1100)], 0, "Auto", "Scandi", 14),
    ("House_15_Stepped", [_rect(1200, 1000), _rect(1200, 700), _rect(800, 700)], 0, "Auto", "Warm", 15),
    ("House_16_OneSpline", [_rect(900, 800), None], 2, "Auto", "Modern", 16),
    ("House_17_LongStair", [_rect(650, 1300), _rect(650, 1300)], 0, "Straight", "Scandi", 17),
]


def houses():
    """[(name, shape, (x, y, z) actor location, yaw, style, seed)]: the actor sits at the footprint's local origin."""
    out = []
    xn = xs = 0.0
    for name, shape, side, style, seed in STREET:
        w = width(shape)
        if side == "N":
            out.append((name, shape, (xn, FRONT, 0.0), -90.0, style, seed))
            xn += w + GAP
        elif side == "S":
            out.append((name, shape, (xs + w, -FRONT, 0.0), 90.0, style, seed))
            xs += w + GAP
        else:
            out.append((name, shape, (max(xn, xs) + 600.0, -FRONT - 200.0, 0.0), 120.0, style, seed))
    return out


def world_points(shape, loc, yaw):
    """The footprint's corners in world space for a house actor at `loc` turned `yaw` (pypcg.interior.footprint.Frame)."""
    return floor_points(SHAPES[shape], loc, yaw, 0, 0.0)


def floor_points(outline, loc, yaw, k, H):
    """A local outline's corners in world space for floor k of a house actor at `loc` turned `yaw`: z = loc z + k H."""
    import math
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    return [(loc[0] + x * ex[0] + y * ey[0], loc[1] + x * ex[1] + y * ey[1], loc[2] + k * H) for x, y in outline]


STREET2 = -6500.0       # the second street's centre line (world y), south of the first street's houses
STOREY_NORTH = ("House_11_TwoStorey", "House_12_FrontTerrace", "House_13_LTerrace", "House_14_Townhouse")


def storeys():
    """[(name, outlines, (x, y, z) actor location, yaw, Floors, StairType, style, seed)]: the multi-storey houses on the
    second street (along world X at y = STREET2), 11-14 on its north side facing -Y, 15-17 on its south side facing +Y."""
    out = []
    xn = xs = 0.0
    for name, outlines, floors, stair, style, seed in STOREYS:
        w = max(p[0] for p in outlines[0]) - min(p[0] for p in outlines[0])
        if name in STOREY_NORTH:
            out.append((name, outlines, (xn, STREET2 + FRONT, 0.0), -90.0, floors, stair, style, seed))
            xn += w + GAP
        else:
            out.append((name, outlines, (xs + w, STREET2 - FRONT, 0.0), 90.0, floors, stair, style, seed))
            xs += w + GAP
    return out
