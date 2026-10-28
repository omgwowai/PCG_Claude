"""PyWorld W2 -- the locations (视频步骤 2：美术放置的兴趣点).

Reads three kinds of level actor as single points (Get Actor Data, GetSinglePoint): PyWorld_Location (its X scale x
100 m is the radius), PyWorld_RiverEnd and PyWorld_RoadExit. Each location moves, within SnapRadius, to the flattest
ground of the final terrain W1 wrote; its radius gives its kind (Town / Village / Hamlet). The higher river end is
the source. A point the terrain does not cover keeps its place with Slope -1."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.world import points as WP, rules

STAGE = 102
RECORD = "w02"
DOC = """PyWorld W2 Locations (地点): the location, river-end and road-exit actors, snapped to flat ground on the
terrain; a location's radius (its X scale x 100 m) gives its kind."""
RANDOM = False
PARAMS = {"SnapRadius": Param(6000.0, "How far a location may move to find flatter ground (cm)", type="Double")}
INPUTS = {"Locations": "points", "RiverEnds": "points", "Exits": "points", "Surface": "surface"}
OUTPUTS = ("Locations", "RiverEnds", "Exits", "Summary")
PROBE_CM = 600.0
STEP_CM = 1500.0


def actors(items):
    """[(loc, scale)] of every point on a pin."""
    out = []
    for v, _t in items:
        if isinstance(v, Points):
            out.extend(zip(v.loc, v.scale))
    return out


def surface_of(items):
    for v, _t in items:
        if hasattr(v, "height"):
            return v
    return None


def slope_at(surface, x, y, h=PROBE_CM):
    zs = [surface.height(x + dx, y + dy) for dx, dy in ((h, 0.0), (-h, 0.0), (0.0, h), (0.0, -h))]
    if any(z is None for z in zs):
        return None
    return math.degrees(math.atan(math.hypot((zs[0] - zs[1]) / (2 * h), (zs[2] - zs[3]) / (2 * h))))


def snap(surface, x, y, radius):
    """(x, y, z, slope): the flattest sample within radius (ties: the closer); the input with z 0, slope -1 when the
    terrain covers none of it."""
    best = None
    m = int(radius // STEP_CM)
    if surface is not None:
        for b in range(-m, m + 1):
            for a in range(-m, m + 1):
                px, py = x + a * STEP_CM, y + b * STEP_CM
                d = math.hypot(px - x, py - y)
                if d > radius:
                    continue
                s = slope_at(surface, px, py)
                if s is not None and (best is None or (s, d) < best[0]):
                    best = ((s, d), px, py)
    if best is None:
        return x, y, 0.0, -1.0
    _key, px, py = best
    return px, py, float(surface.height(px, py)), float(best[0][0])


def run(inputs, params, ctx):
    surface = surface_of(inputs.get("Surface", []))
    locs = sorted(actors(inputs.get("Locations", [])), key=lambda a: (-a[1][0], a[0][1], a[0][0]))
    rows, off, worst = [], 0, 0.0
    for i, (loc, scale) in enumerate(locs):
        radius = float(scale[0]) * 10000.0
        x, y, z, s = snap(surface, loc[0], loc[1], params["SnapRadius"])
        off += s < 0
        worst = max(worst, s)
        rows.append({"loc": (x, y, z), "Id": i, "Kind": rules.kind_of(radius), "Radius": radius, "Slope": s})

    def placed(items):
        out = []
        for loc, _s in sorted(actors(items), key=lambda a: (a[0][1], a[0][0])):
            h = surface.height(loc[0], loc[1]) if surface is not None else None
            out.append((loc[0], loc[1], float(h) if h is not None else 0.0))
        return out
    ends = placed(inputs.get("RiverEnds", []))
    top = max(range(len(ends)), key=lambda i: ends[i][2]) if ends else None
    end_rows = [{"loc": p, "Role": "Source" if i == top else "Outlet"} for i, p in enumerate(ends)]
    exit_rows = [{"loc": p, "Id": i} for i, p in enumerate(placed(inputs.get("Exits", [])))]
    out = {"Locations": [], "RiverEnds": [], "Exits": []}
    if rows:
        types = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}
        out["Locations"] = [(WP.table_points(rows, types), ["Location"])]
    if end_rows:
        out["RiverEnds"] = [(WP.table_points(end_rows, {"Role": "String"}), ["RiverEnd"])]
    if exit_rows:
        out["Exits"] = [(WP.table_points(exit_rows, {"Id": "Int32"}), ["RoadExit"])]
    summary = {"locations": len(rows), "river_ends": len(end_rows), "exits": len(exit_rows),
               "max_center_slope_deg": float(worst), "off_terrain": int(off)}
    out["Summary"] = [(WP.summary(summary), ["Summary"])]
    return out
