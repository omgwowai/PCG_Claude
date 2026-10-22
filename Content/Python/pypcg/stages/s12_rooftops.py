"""Stage 12 -- Rooftops (PCG_3_3_2_Rooftops, 屋顶设备): which rooftop gets which assemblies.

The official graph is 22 nodes (13 computation, 5 generation); `docs/pypcg/stages/s12.md` names the official node
behind every step. This is the stage's MAIN Python node, before the four kept fitting-asset nodes;
`s12_rooftops_assemblies` runs after two of them, before the kept spawner.

Every rooftop arrives as the closed linear spline stage 11's building nodes made (identity transform, flat). An
area primitive reads such a spline through `InputsProcessing_ForcePolygon` (`CreatePolygon2D`); the kept
fitting nodes do the same, so a rooftop that is only filtered is FORWARDED as the very spline it came in as
(`FORWARD_SPLINES`): the fitting node then builds the official polygon itself, bit for bit (traps.md 62).

The chain (official node names in brackets):

  CLASS     the class tag, exactly [FilterDataByTag_0 SmallRooftops / _2 MediumRooftops / _3 LargeRooftops]
  AREA      each rooftop as CreatePolygon2D makes it, `@data.$area` strictly greater than 300 / 800 / 500 m2
            [Subgraph_9 / Subgraph_6 / Subgraph_5 Filter_Areas_BySize, Operator Greater]
  HEIGHT    the large ones above 500 m2 [Reroute_0]: the AVERAGE of their ToPoint vertices' z (`AttributeReduce`'s
            default operation; the node is titled "Reduce Z To Max Height", it does not take the max)
            [AttributeReduce_0] onto `@data.height` [CopyAttributes_0], strictly greater than 7000 cm
            [FilterDataByAttribute_1, Greater]. A WORLD z: the roof, not the building, above 70 m
  OFFSETS   `Transform_Offset` (PerPoints, non-absolute) on a polygon reads its ToPoint vertices, moves them
            and builds a NEW polygon from them (`CreatePolygon2D` on points: MakePolygon2DData mirrors it); on a
            spline it moves the control points [Subgraph_8 -8 cm, Subgraph_10 -20 cm]. Polygons out first, then
            splines (the CoreProcess's output order)
  OUT       SmallAssemblyAreas  -> Subgraph_2 Place Small Rooftop Assemblies: -8 cm, the large (> 500 and not),
                                   the medium > 800, then every small rooftop (spline)
            WfcAreas            -> Subgraph_7 Place WFC Rooftop Assemblies: the large <= 500, the small > 300,
                                   the large > 500 at <= 7000 cm (forwarded)
            SkyscraperAreas     -> Subgraph_3 Place Skyscraper Rooftop Assemblies: -20 cm, the large > 500 above
                                   7000 cm
            VentAreas           -> Subgraph_11 Place AC Vents & Roof Houses: the medium <= 800, the small <= 300
                                   (forwarded)

No random numbers: every choice is a filter.
"""
from pypcg.geo import Polygon, Spline
from pypcg.geo import frames as F

STAGE = 12
DOC = """Rooftops (屋顶设备): every building rooftop from the building stage gets rooftop assemblies by its class and
size -- small assemblies on most of them (lowered 8 cm onto the roof), WFC assemblies on the mid-sized ones, AC vents
and roof houses on the smallest, and skyscraper assemblies (lowered 20 cm) on large roofs higher than 70 m; the WFC
assemblies that would overlap a small one are dropped."""
RANDOM = False
FORWARD_SPLINES = True
PARAMS = {}
INPUTS = {"Rooftops": "spline"}
OUTPUTS = ("SmallAssemblyAreas", "WfcAreas", "SkyscraperAreas", "VentAreas")

CLASS_TAGS = ("SmallRooftops", "MediumRooftops", "LargeRooftops")     # FilterDataByTag_0 / _2 / _3
SIZE_M2 = {"SmallRooftops": 300.0, "MediumRooftops": 800.0, "LargeRooftops": 500.0}   # Subgraph_9 / 6 / 5
SKYSCRAPER_Z_CM = 7000.0           # FilterDataByAttribute_1 Threshold (Greater)
SMALL_OFFSET_CM = -8.0             # Subgraph_8 offset.Z
SKYSCRAPER_OFFSET_CM = -20.0       # Subgraph_10 offset.Z
TYPE_TAGS = ("Type:Point", "Type:Spline", "Type:ClosedSpline", "Type:Polygon2D", "Type:Surface", "Type:Texture2D",
             "Type:Volume")


class Roof:
    """One rooftop between the nodes: the input spline as it came in (forwarded unchanged), its tags, and the
    polygon `CreatePolygon2D` makes of it (`geo.frames.SplinePolygon`), built when first asked for."""

    def __init__(self, spline, tags):
        self.spline = spline
        self.tags = list(tags)
        self._poly = None

    @property
    def poly(self):
        if self._poly is None:
            self._poly = F.SplinePolygon(self.spline)
        return self._poly


# ---- the steps ------------------------------------------------------------------------------------
def by_class(items):
    """FilterDataByTag_0 / _2 / _3: {class tag: [Roof]} in input order; only closed splines are areas."""
    out = {tag: [] for tag in CLASS_TAGS}
    for v, tags in items:
        if not (isinstance(v, Spline) and v.closed and len(v.points) >= 3):
            continue
        for tag in CLASS_TAGS:
            if tag in tags:
                out[tag].append(Roof(v, tags))
    return out


def by_size(roofs, size_m2):
    """`Filter_Areas_BySize` (Operator Greater): (selected, unselected) -- `@data.$area` > Size x 10 000."""
    limit = float(size_m2) * 10000.0
    sel = [r for r in roofs if r.poly.area > limit]
    uns = [r for r in roofs if not r.poly.area > limit]
    return sel, uns


def average_z(roof):
    """AttributeReduce_0 on `$position.Z` with its DEFAULT operation, Average: the polygon's ToPoint vertices' z,
    summed in order and multiplied by `float(1 / n)` (traps.md 72)."""
    zs = [v[2] for v in roof.poly.vertices]
    s = 0.0
    for z in zs:
        s += z
    return s * F.f32(1.0 / len(zs)) if zs else 0.0


def by_height(roofs):
    """CopyAttributes_0 + FilterDataByAttribute_1: (inside = above SKYSCRAPER_Z_CM, outside, heights)."""
    heights = [average_z(r) for r in roofs]
    inside = [r for r, h in zip(roofs, heights) if h > SKYSCRAPER_Z_CM]
    outside = [r for r, h in zip(roofs, heights) if not h > SKYSCRAPER_Z_CM]
    return inside, outside, heights


def offset_polygon(roof, dz):
    """`Transform_Offset` on a polygon (PerPoints, non-absolute): `GetSplineControlPoints` reads its ToPoint
    vertices, `TransformPoints` moves each by its own rotation applied to (0, 0, dz) (`FTransform(rotation).
    TransformPosition(offset)`), and `CreatePolygon2D` builds a new polygon from those 3D points (what
    MakePolygon2DData does with the port's polygon). The vertices' z differ in the last bit (Newell's normal is a hair
    off vertical, so is each vertex's rotation), so every vertex keeps its own z (`Polygon.zs`)."""
    from pypcg.geo.plane import quat_rotate
    moved = []
    for v, q in zip(roof.poly.vertices, roof.poly.rotations):
        d = quat_rotate(q, (0.0, 0.0, float(dz)))
        moved.append((v[0] + d[0], v[1] + d[1], v[2] + d[2]))
    return Polygon([(p[0], p[1]) for p in moved], [], moved[0][2] if moved else 0.0, zs=[p[2] for p in moved])


def offset_spline(roof, dz):
    """`Transform_Offset` on a spline (`OffsetSpline` by each control point's moved-minus-old position): every
    control point z + dz, the rest as it was. The control points' rotations are not readable (traps.md 63);
    `CreatePolygon2D`, the only reader downstream, uses positions alone."""
    s = roof.spline
    return Spline([(p[0], p[1], p[2] + dz) for p in s.points], closed=s.closed, linear=s.linear,
                  tangents=s.tangents)


def _polygon_tags(roof, selection):
    return sorted({t for t in roof.tags if t not in TYPE_TAGS} | {"Type:Polygon2D", selection})


def _forward(roof, selection):
    return (roof.spline, sorted(set(roof.tags) | {selection}))


def rooftops(items):
    """{output pin: [(value, tags)]} and the counts (notes)."""
    cls = by_class(items)
    s9_sel, s9_uns = by_size(cls["SmallRooftops"], SIZE_M2["SmallRooftops"])        # Subgraph_9
    s6_sel, s6_uns = by_size(cls["MediumRooftops"], SIZE_M2["MediumRooftops"])      # Subgraph_6
    s5_sel, s5_uns = by_size(cls["LargeRooftops"], SIZE_M2["LargeRooftops"])        # Subgraph_5
    inside, outside, heights = by_height(s5_sel)                                     # Reroute_0 .. Filter_1

    small = ([(offset_polygon(r, SMALL_OFFSET_CM), _polygon_tags(r, "Selected")) for r in s5_sel]
             + [(offset_polygon(r, SMALL_OFFSET_CM), _polygon_tags(r, "Unselected")) for r in s5_uns]
             + [(offset_polygon(r, SMALL_OFFSET_CM), _polygon_tags(r, "Selected")) for r in s6_sel]
             + [(offset_spline(r, SMALL_OFFSET_CM), sorted(r.tags)) for r in cls["SmallRooftops"]])
    wfc = ([_forward(r, "Unselected") for r in s5_uns] + [_forward(r, "Selected") for r in s9_sel]
           + [_forward(r, "Selected") for r in outside])
    sky = [(offset_polygon(r, SKYSCRAPER_OFFSET_CM), _polygon_tags(r, "Selected")) for r in inside]
    vent = [_forward(r, "Unselected") for r in s6_uns] + [_forward(r, "Unselected") for r in s9_uns]
    out = {"SmallAssemblyAreas": small, "WfcAreas": wfc, "SkyscraperAreas": sky, "VentAreas": vent}
    counts = {"small": len(cls["SmallRooftops"]), "medium": len(cls["MediumRooftops"]),
              "large": len(cls["LargeRooftops"]), "small>300": len(s9_sel), "medium>800": len(s6_sel),
              "large>500": len(s5_sel), "large>500 above 70m": len(inside)}
    return out, counts, heights


def run(inputs, params, ctx):
    out, counts, _h = rooftops(inputs.get("Rooftops", []))
    ctx.notes.append("rooftops: %s; areas small %d, WFC %d, skyscraper %d, vents %d" % (
        ", ".join("%s %d" % kv for kv in counts.items()), len(out["SmallAssemblyAreas"]), len(out["WfcAreas"]),
        len(out["SkyscraperAreas"]), len(out["VentAreas"])))
    return out
