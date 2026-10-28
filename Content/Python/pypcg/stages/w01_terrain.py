"""PyWorld W1 -- the valley terrain (视频步骤 0：地形底图).

Every vertex of the base mesh terrain (a 3 km query) gets the valley's height: a floor that follows the
`PyWorld_Valley` axis spline (its control points carry the floor height) with a 2 % cross slope and low noise,
walls rising over `WallWidth` to ridges `RidgeHeight` above the floor (domain-warped value noise for their height,
ridged noise for crests and gullies), and a fall to the sea floor (-600 cm) between EdgeStart and EdgeEnd from the
centre. `Mountain` (0 on the floor .. 1 up the walls) is written for the native erosion that follows, which only
works the mountains (its MaskAttribute). Pure: no unreal import."""
import bisect
import math

from pypcg.geo import Points, Spline
from pypcg.stage_api import Param
from pypcg.world import SEA_Z, VERTEX_CM, noise, points as WP
from pypcg.world.grid import Lattice
from pypcg.world.terraform import smoothstep

STAGE = 101
RECORD = "w01"
DOC = """PyWorld W1 Terrain (地形): the valley floor along the PyWorld_Valley spline, walls up to the ridges, noise on
the mountains and a fall to the sea at the edge; writes Mountain (0 floor .. 1 walls) for the native erosion."""
RANDOM = True
PARAMS = {
    "FloorHalfWidth": Param(25000.0, "Half width of the valley floor (cm)", type="Double"),
    "WallWidth": Param(40000.0, "Horizontal run of the valley walls (cm)", type="Double"),
    "RidgeHeight": Param(18000.0, "Ridge height above the valley floor (cm)", type="Double"),
    "EdgeStart": Param(115000.0, "Distance from the centre where the land starts falling to the sea (cm)", type="Double"),
    "EdgeEnd": Param(148000.0, "Distance from the centre where the land reaches the sea floor (cm)", type="Double"),
}
INPUTS = {"MeshTerrain": "points", "Valley": "spline"}
OUTPUTS = ("Terrain", "Summary")


def axis_table(items):
    """The valley axis as points sorted by y (the engine's polyline when there is one)."""
    pts = []
    for v, _t in items:
        if isinstance(v, Spline):
            pts.extend(tuple(p) for p in (v.polyline or v.points))
    return sorted(pts, key=lambda p: p[1])


def axis_at(table, y):
    """(axis x, floor z) at y, clamped to the axis's ends; (0, 0) without an axis."""
    if not table:
        return 0.0, 0.0
    ys = [p[1] for p in table]
    i = bisect.bisect_left(ys, y)
    if i <= 0:
        return table[0][0], table[0][2]
    if i >= len(table):
        return table[-1][0], table[-1][2]
    a, b = table[i - 1], table[i]
    t = 0.0 if b[1] == a[1] else (y - a[1]) / (b[1] - a[1])
    return a[0] + (b[0] - a[0]) * t, a[2] + (b[2] - a[2]) * t


def height(x, y, table, p, seed):
    """(z, mountain) of one vertex."""
    ax, floor = axis_at(table, y)
    d = abs(x - ax)
    fw, ww = p["FloorHalfWidth"], p["WallWidth"]
    z = floor + 120.0 * noise.fbm(x / 9000.0, y / 9000.0, seed, 3) + 0.02 * min(d, fw)
    t = smoothstep(fw, fw + ww, d)
    if t > 0.0:
        wx = x + 6000.0 * noise.fbm(x / 30000.0, y / 30000.0, seed + 11, 2)
        wy = y + 6000.0 * noise.fbm(x / 30000.0, y / 30000.0, seed + 12, 2)
        ridge = p["RidgeHeight"] * (0.75 + 0.5 * noise.value(wx / 50000.0, wy / 50000.0, seed + 21))
        detail = 0.2 * p["RidgeHeight"] * noise.ridged(wx / 14000.0, wy / 14000.0, seed + 31, 4)
        z += t ** 1.3 * (ridge + detail * t)
    f = smoothstep(p["EdgeStart"], p["EdgeEnd"], max(abs(x), abs(y)))
    return z + (SEA_Z - z) * f, t


def run(inputs, params, ctx):
    table = axis_table(inputs.get("Valley", []))
    out, n, nan, zmax = [], 0, 0, -1e30
    for v, _t in inputs.get("MeshTerrain", []):
        if not isinstance(v, Points) or not len(v):
            continue
        lat, ks = Lattice.from_locs(v.loc, VERTEX_CM)
        mountain = []
        for k, (x, y, _z) in zip(ks, v.loc):
            z, m = height(x, y, table, params, ctx.seed)
            if z != z:
                nan += 1
                z = SEA_Z
            lat.z[k] = z
            mountain.append(m)
            zmax = max(zmax, z)
        n += len(v)
        out.append((WP.with_heights(v, lat, ks, {"Mountain": ("Double", mountain)}), ["Terrain"]))
    err = 0.0
    if table:
        for q in range(9):
            y = table[0][1] + (table[-1][1] - table[0][1]) * (q + 0.5) / 9.0
            ax, floor = axis_at(table, y)
            if max(abs(ax), abs(y)) < params["EdgeStart"]:
                err = max(err, abs(height(ax, y, table, params, ctx.seed)[0] - floor))
    ctx.notes.append("%d vertices, ridge max %.0f cm" % (n, zmax))
    summary = {"points": n, "ridge_max_cm": float(zmax if n else 0.0), "floor_err_max_cm": float(err), "nan": nan}
    return {"Terrain": out, "Summary": [(WP.summary(summary), ["Summary"])]}
