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
    import math
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    return [(loc[0] + x * ex[0] + y * ey[0], loc[1] + x * ex[1] + y * ey[1], loc[2]) for x, y in SHAPES[shape]]
