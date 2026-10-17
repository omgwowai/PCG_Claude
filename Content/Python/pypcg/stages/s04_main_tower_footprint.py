"""Stage 4 -- MainTowerFootprint (PCG_2_1_MainTower_Footprint, 主塔占位).

Publishes the hero tower's footprint as one closed hexagonal spline, built from the volume's OWN
transform: the shape is centred on the volume actor's location, turned by its yaw, and its Z is the
volume's Z. The official graph reads that transform inside the `Create_Spline_Shape` primitive
(`GetActorData_1`, `Mode = GetSinglePoint`) and the slim graph delivers the same point on the `Volume`
pin, so the stage takes no scene reads. Replaces the 6-node graph (2 parameter getters, the primitive
with its 52-node CoreProcess, a reroute, a debug offset and the debug mesh)."""
from pypcg import geo
from pypcg.geo import Spline
from pypcg.stage_api import Param, volume_point

STAGE = 4
DOC = """MainTowerFootprint (主塔占位): the hero tower's footprint as a closed hexagonal spline, built
from the volume's own transform. RectWidth is twice the radius the hexagon is built on: its two
vertices on the local X axis sit RectWidth / 2 from the centre, so at RectLength = RectWidth the
shape is regular and RectWidth is its corner-to-corner span (the flat-to-flat width is RectWidth x
sqrt(3) / 2). RectLength is the ratio the shape is stretched along its local Y (1 = a regular
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


def hexagon(center, width, length, yaw_deg=0.0):
    """The polygon `Create_Spline_Shape_CoreProcess` builds for Ngon = 6: `CreatePointsSphere_0` puts
    `LongitudinalSegments = Ngon` points on a circle of radius `Width / 2`, the convex hull keeps
    them, and `MakeVectorAttribute_1`'s `Scale` = (1, Length / Width, 1) stretches them along local
    Y. The 6-gon takes the sphere path no matter what (its `Ngon == 4` test fails), so this is the
    Ngon >= 5 branch, not the grid branch. Center is (x, y); Z comes from the caller."""
    ratio = (length / width) if width else 1.0
    return geo.ngon(center, width / 2.0, N, start_deg=START_DEG, step_deg=STEP_DEG,
                    y_scale=ratio, yaw_deg=yaw_deg)


def radii(width, length):
    """The six vertex distances from the centre, as the brief's two radii -- derived, not read back
    from `ngon`, so a check that uses it cannot agree with its own bug.

    With `R = Width / 2` (the sphere's radius) and `r = Length / Width` (the local-Y stretch), the
    six local angles are the builder's `-60 - 60k` degrees: -60, -120, -180, -240, -300, -360. Two
    of them (-180 and -360) lie on the local X axis and sit at `R`; the other four are
    `(R cos a, R r sin a)` with |cos a| = 1/2 and |sin a| = sqrt(3)/2, i.e. at
    `R sqrt(1/4 + 3 r^2 / 4)`. So the smallest vertex radius is `R` and the largest is
    `R sqrt(1/4 + 3 r^2 / 4)` -- at `r = 1` both are `R` (a regular hexagon). Neither is the
    APOTHEM, `R sqrt(3) / 2`: no vertex sits on the flat-to-flat circle. And the widest vertex is
    never `R r` either -- it approaches `R r sqrt(3) / 2` as `r` grows, and is exact as written only
    by the square root. Returns the six in the published vertex order."""
    R = width / 2.0
    r = (length / width) if width else 1.0
    far = R * (0.25 + 0.75 * r * r) ** 0.5
    return [far, far, R, far, far, R]


def run(inputs, params, ctx):
    loc, yaw = volume_point(inputs)
    if loc is None:
        return {"Footprint": []}
    width, length = float(params["RectWidth"]), float(params["RectLength"])
    ring = hexagon((loc[0], loc[1]), width, length, yaw)
    return {"Footprint": [(Spline([(x, y, loc[2]) for x, y in ring], closed=True, linear=True),
                           ["Footprint"])]}
