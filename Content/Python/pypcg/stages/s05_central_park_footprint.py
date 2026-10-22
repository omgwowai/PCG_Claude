"""Stage 5 -- CentralParkFootprint (PCG_2_2_CentralPark_Footprint, 中央公园范围).

Publishes the central park's footprint as one closed four-vertex spline, built from the volume's OWN
transform: the rectangle is centred on the volume actor's location and turned by its yaw; its Z is 0
(the official graph pins `$Position.Z` to 0, `AttributeMathsOp_0`, after the shape is built).
Replaces the 3-node graph: the `Create_Spline_Shape` primitive (`Park_Footprint`, 52-node CoreProcess)
and the `$Position.Z` maths node; the debug mesh goes."""
from pypcg import geo
from pypcg.geo import Spline
from pypcg.stage_api import Param, volume_point, volume_quat

STAGE = 5
DOC = """CentralParkFootprint (中央公园范围): the central park's footprint as a closed four-vertex
spline built from the volume's own transform, at Z 0. RectWidth is the rectangle's width (local X),
RectLength its length (local Y); the official demo is 1000 x 200 m. Sizes in cm."""
RANDOM = False
PARAMS = {
    "RectWidth": Param(100000.0, "Width of the central park footprint in centimeters", type="Float"),
    "RectLength": Param(20000.0, "Length of the central park footprint in centimeters", type="Float"),
}
INPUTS = {"Volume": "points"}
OUTPUTS = ("Footprint",)

# The official order: `CreateSpline_1` builds the grid's corner points clockwise,
# `SplineDirection_0 ForceCounterClockwise` gives a NEGATIVE standard area (traps.md 41), and
# `geo.rect`'s default order is that order. Keep it: later stages read these vertices.
ORDER = ((-1, 1), (1, 1), (1, -1), (-1, -1))
Z = 0.0


def rectangle(center, width, length, yaw_deg=0.0, quat=None):
    """The polygon `Create_Spline_Shape_CoreProcess` builds for Ngon = 4: `CreatePointsGrid_0` emits
    the cell corners of a grid `Width` x `Length` around the origin (one cell, `GridExtents` =
    (Width, Length) / 2), `FindConvexHull2D_0` keeps the four corners, and `AttributeTransformOp_2`
    composes them with the volume transform. Corners in the official order (see ORDER).

    The composition is `geo.place`: the volume's QUATERNION rotate in UE's operation order, then the
    translation. With the actor's own quaternion (`stage_api.volume_quat`) this reproduces the demo
    park's eight coordinates BIT FOR BIT (measured 2026-10-19); a cos/sin turn by the yaw is ~1e-11
    cm off, and stage 7 reads those bits. Without a quaternion the yaw's is used."""
    local = [(sx * (width / 2.0), sy * (length / 2.0)) for sx, sy in ORDER]
    return geo.place(local, quat or geo.quat_from_yaw(yaw_deg), center)


def run(inputs, params, ctx):
    loc, yaw = volume_point(inputs)
    if loc is None:
        return {"Footprint": []}
    ring = rectangle((loc[0], loc[1]), float(params["RectWidth"]), float(params["RectLength"]), yaw,
                     volume_quat(inputs))
    return {"Footprint": [(Spline([(x, y, Z) for x, y in ring], closed=True, linear=True),
                           ["Footprint"])]}
