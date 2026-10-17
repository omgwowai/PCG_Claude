"""Stage 4 -- MainTowerFootprint (PCG_2_1_MainTower_Footprint, 主塔占位).

Publishes the hero tower's footprint as one closed hexagonal spline, built from the volume's OWN
transform: the shape is centred on the volume actor's location, turned by its yaw, and its Z is the
volume's Z. The official graph reads that transform inside the `Create_Spline_Shape` primitive
(`GetActorData_1`, `Mode = GetSinglePoint`) and the slim graph delivers the same point on the `Volume`
pin, so the stage takes no scene reads. Replaces the 6-node graph (2 parameter getters, the primitive
with its 52-node CoreProcess, a reroute, a debug offset and the debug mesh)."""
from pypcg import geo
from pypcg.geo import Spline
from pypcg.stage_api import Param

STAGE = 4
DOC = """MainTowerFootprint (主塔占位): the hero tower's footprint as a closed hexagonal spline, built
from the volume's own transform. RectWidth is the hexagon's width across the flats (the circumradius
is RectWidth / 2); RectLength is the ratio the shape is stretched along its local Y (1 = a regular
hexagon). Sizes in cm."""
RANDOM = False
PARAMS = {
    "RectWidth": Param(16000.0, "Width of the landmark rectangle in centimeters", type="Float"),
    "RectLength": Param(16000.0, "Length of the landmark rectangle in centimeters", type="Float"),
}
INPUTS = {"Volume": "points"}
OUTPUTS = ("Footprint",)

N = 6
START_DEG = -60.0          # the official hexagon's first vertex is (R/2, -R*sqrt(3)/2)
STEP_DEG = -60.0           # clockwise: `SplineDirection_0 ForceCounterClockwise` leaves a NEGATIVE
                           # standard area (traps.md 41); geo.ngon's default order is that order.


def volume_point(inputs):
    """(loc, yaw) of the volume, from the single point `Get Actor Data (GetSinglePoint)` writes on
    the `Volume` pin. yaw is `rot[1]`: convert._points_of stores a rotator as (pitch, yaw, roll)."""
    for value, _tags in inputs.get("Volume", []):
        loc, rot = getattr(value, "loc", None), getattr(value, "rot", None)
        if loc:
            r = rot[0] if rot else (0.0, 0.0, 0.0)
            return tuple(loc[0]), float(r[1])
    return None, 0.0


def hexagon(center, width, length, yaw_deg=0.0):
    """The polygon `Create_Spline_Shape_CoreProcess` builds for Ngon = 6: `CreatePointsSphere_0` puts
    `LongitudinalSegments = Ngon` points on a circle of radius `Width / 2`, the convex hull keeps
    them, and `MakeVectorAttribute_1`'s `Scale` = (1, Length / Width, 1) stretches them along local
    Y. The 6-gon takes the sphere path no matter what (its `Ngon == 4` test fails), so this is the
    Ngon >= 5 branch, not the grid branch. Center is (x, y); Z comes from the caller."""
    ratio = (length / width) if width else 1.0
    return geo.ngon(center, width / 2.0, N, start_deg=START_DEG, step_deg=STEP_DEG,
                    y_scale=ratio, yaw_deg=yaw_deg)


def run(inputs, params, ctx):
    loc, yaw = volume_point(inputs)
    if loc is None:
        return {"Footprint": []}
    width, length = float(params["RectWidth"]), float(params["RectLength"])
    ring = hexagon((loc[0], loc[1]), width, length, yaw)
    return {"Footprint": [(Spline([(x, y, loc[2]) for x, y in ring], closed=True, linear=True),
                           ["Footprint"])]}
