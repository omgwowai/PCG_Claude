"""Stage 0: the host probe (ruling N9). Not one of the 18 steps. It runs once in the editor to check
every path between PCG data and pypcg.geo values: it reads the volume's own point, a terrain
surface, a spline and an empty pin, and writes a polygon with a hole, a closed spline, points with
attributes, a parameter set, a report of what it read, and optionally many points (timing)."""
from pypcg.geo import ParamSet, Points, Polygon, Spline
from pypcg.stage_api import Param

STAGE = 0
VERSION = 1
DOC = "PyPCG host probe; not part of the town."
RANDOM = True
PARAMS = {"Size": Param(5000.0, "Half size of the probe square (cm)"), "Label": "probe", "Flag": True, "Count": 3,
          "BenchPoints": Param(0, "Also write this many plain points, to time the point writer")}
INPUTS = {"Volume": "points", "Terrain": "surface", "Spline": "spline", "Empty": "any"}
OUTPUTS = ("Area", "Line", "Points", "Params", "Report", "Bench")


def run(inputs, params, ctx):
    vol = inputs["Volume"][0][0]
    cx, cy, cz = vol.loc[0]
    s = params["Size"]
    ring = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]
    q = s / 4.0
    hole = [(cx - q, cy - q), (cx - q, cy + q), (cx + q, cy + q), (cx + q, cy - q)]
    surfaces = [v for v, _ in inputs["Terrain"] if hasattr(v, "height")]
    z = surfaces[0].height(cx, cy) if surfaces else None
    splines = [v for v, _ in inputs["Spline"] if isinstance(v, Spline)]
    pts = Points()
    pts.declare("Mesh", "SoftObjectPath")
    pts.declare("Weight", "Double")
    for i in range(params["Count"]):
        pts.add((cx + 1000.0 * i, cy, cz), rot=(0.0, 30.0 * i, 0.0), Mesh="/Engine/BasicShapes/Cube.Cube", Weight=0.5 * i)
    bench = Points()
    for i in range(params["BenchPoints"]):
        bench.add((cx + (i % 1000) * 10.0, cy + (i // 1000) * 10.0, cz))
    report = ParamSet({
        "Version": VERSION, "TerrainZ": z if z is not None else -1.0e9,
        "TerrainKinds": ",".join(sorted(getattr(v, "kind", type(v).__name__) for v, _ in inputs["Terrain"])),
        "SplineCount": len(splines), "SplineControl": len(splines[0].points) if splines else 0,
        "SplinePolyline": len(splines[0].polyline or []) if splines else 0,
        "SplineClosed": bool(splines and splines[0].closed), "EmptyCount": len(inputs["Empty"]),
        "Label": params["Label"], "Flag": params["Flag"], "Draw": ctx.rng.random()})
    return {"Area": [(Polygon(ring, [hole], z=cz), ["PyProbeArea"])],
            "Line": [(Spline([(x, y, cz) for x, y in ring], closed=True), ["PyProbeLine"])],
            "Points": [(pts, ["PyProbePoints"])],
            "Params": [(ParamSet({"A": 1.5, "Name": "x"}), ["PyProbeParams"])],
            "Report": [(report, ["PyProbeReport"])],
            "Bench": [(bench, ["PyProbeBench"])]}
