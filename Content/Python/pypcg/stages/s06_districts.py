"""Stage 6 -- Districts (PCG_3_1_1_Districts, 街区骨架).

Cuts the City outline (actor tag City) with the arteries (tag Arteries) into districts, splits each
district once near its middle (the collector roads), sorts the pieces by area into Undividable /
Small / Medium / Large districts, and lays a road grid over every dividable district (the local
roads). Replaces the official 75-node graph, about 560 nodes counting the primitives it calls. Ported
from the 2026-10-15 spike, which matched the official output to 0.0034 m2 when given the official
split ratios (spike report, table 1)."""
from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.stage_api import Param

STAGE = 6
DOC = """Districts (街区骨架): cuts the City outline (actor tag City) with the arteries (tag Arteries),
splits each district once, sorts the pieces by area and grids the dividable ones. Areas are in m2,
grid spacings in cm. Outputs ArteryRoads, CollectorRoads and localRoads (splines) and
UndividableDistricts, SmallDistricts, MediumDistricts and LargeDistricts (areas)."""
RANDOM = True
PARAMS = {
    "Dividable_district_Limit": Param(150000.0, "Pieces larger than this (m2) get a road grid", category="Sizes"),
    "SmallMediumThreshold": Param(200000.0, "Small / Medium boundary (m2)", category="Sizes"),
    "MediumLargeThreshold": Param(500000.0, "Medium / Large boundary (m2)", category="Sizes"),
    "SmallGridWidth": Param(6000.0, "Small districts: spacing of the roads across the long edge (cm)", category="Grid"),
    "SmallGridLength": Param(3000.0, "Small districts: spacing of the roads along the long edge (cm)", category="Grid"),
    "MediumGridWidth": Param(12000.0, "Medium districts: spacing across the long edge (cm)", category="Grid"),
    "MediumGridLength": Param(6000.0, "Medium districts: spacing along the long edge (cm)", category="Grid"),
    "LargeGridWidth": Param(24000.0, "Large districts: spacing across the long edge (cm)", category="Grid"),
    "LargeGridLength": Param(12000.0, "Large districts: spacing along the long edge (cm)", category="Grid"),
}
INPUTS = {"City": "spline", "Arteries": "spline"}
OUTPUTS = ("ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
           "MediumDistricts", "LargeDistricts")

# Fixed in the official graph (Sub_districts overrides; Filter_Areas_BySize operators are Greater).
SPLIT_ITERATIONS = 1
SPLIT_MIN_AREA_M2 = 1000.0
SPLIT_FROM_CENTER = 0.2        # MaxSplitDistancFromCenter, clamped to [0.05, 0.45]: ratios in [0.3, 0.7]
CLASSES = (("SmallDistricts", "Small"), ("MediumDistricts", "Medium"), ("LargeDistricts", "Large"))


def ring_of(spline):
    """The spline's polyline in the XY plane (the official graph sets $Position.Z to 0)."""
    return geo.drop_closing(geo.xy(spline.polyline or spline.points))


def flat(spline):
    tangents = [((a[0], a[1], 0.0), (b[0], b[1], 0.0)) for a, b in spline.tangents] if spline.tangents else None
    return Spline([(p[0], p[1], 0.0) for p in spline.points], spline.closed, spline.linear, tangents)


def _line(seg):
    return Spline([(x, y, 0.0) for x, y in seg])


def ratio_fn(rng):
    c = min(max(SPLIT_FROM_CENTER, 0.05), 0.45)
    return lambda ring: 0.5 - c + 2.0 * c * rng.random()


def classify(area_m2, params):
    if not area_m2 > params["Dividable_district_Limit"]:
        return "UndividableDistricts"
    if not area_m2 > params["SmallMediumThreshold"]:
        return "SmallDistricts"
    if not area_m2 > params["MediumLargeThreshold"]:
        return "MediumDistricts"
    return "LargeDistricts"


def districts(inputs, params, ops, ratio):
    """Everything run() does, with the split ratios supplied by ratio(ring) (run() draws them; the V1
    oracle check in pypcg/checks/s06.py supplies the official ones)."""
    out = {pin: [] for pin in OUTPUTS}
    cities = [v for v, _ in inputs["City"] if isinstance(v, Spline) and v.closed]
    arteries = [ring_of(v) for v, _ in inputs["Arteries"] if isinstance(v, Spline) and not v.closed]
    for city in cities:
        ring = geo.ccw(ring_of(city))
        out["ArteryRoads"].append((flat(city), ["ArteryRoads"]))                  # the outline itself
        for path in arteries:
            out["ArteryRoads"] += [(_line(seg), ["ArteryRoads"]) for seg in geo.clip_path(path, ring)]
        pieces = ops.cut_with_paths(ring, arteries) if arteries else [ring]
        pieces = [r for r in pieces if abs(geo.signed_area(r)) >= geo.SLIVER_CM2]
        areas, collectors = [], []
        for d in pieces:
            geo.recursive_split(d, ops, SPLIT_ITERATIONS, SPLIT_MIN_AREA_M2 * 1e4, ratio, areas, collectors)
        out["CollectorRoads"] += [(_line(seg), ["CollectorRoads"]) for seg in collectors]
        for r in areas:
            tag = classify(abs(geo.signed_area(r)) / 1e4, params)
            out[tag].append((Polygon(r), [tag]))
    for tag, size in CLASSES:
        for poly, _ in out[tag]:
            for _axis, seg in geo.grid_lines(poly.outer, params[size + "GridWidth"], params[size + "GridLength"]):
                out["localRoads"].append((_line(seg), ["localRoads"]))
    return out


def run(inputs, params, ctx):
    return districts(inputs, params, ctx.ops, ratio_fn(ctx.rng))
