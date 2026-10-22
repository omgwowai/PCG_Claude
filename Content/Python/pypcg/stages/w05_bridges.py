"""PyWorld W5 -- bridges (视频步骤 5：路跨河处由专门的工具生成桥).

Every crossing of a road with the river centre line becomes a bridge: span = river width / |sin(angle)| + two
EndClearance (capped at 60 m), deck at the road's height (W4 raised it), a rail every 4 m on both edges, an
abutment at each end and a pier to the river bed when the span is over PierSpan. Grey-box meshes."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, geom, points as WP

STAGE = 105
RECORD = "w05"
DOC = """PyWorld W5 Bridges (桥): a deck, rails, abutments and a pier wherever a road crosses the river."""
RANDOM = False
PARAMS = {"EndClearance": Param(600.0, "Deck length beyond the water on each side (cm)", type="Double"),
          "PierSpan": Param(1400.0, "Spans longer than this get a pier (cm)", type="Double")}
INPUTS = {"Upstream": "any"}
OUTPUTS = ("Bridges", "Parts", "Summary")
MAX_SPAN = 6000.0
RAIL_CM = 400.0


def bridge_rows(items):
    out = []
    for v, tags in items:
        if isinstance(v, Points) and "Bridge" in tags:
            for r in WP.rows_of(v):
                out.append({"x": r["loc"][0], "y": r["loc"][1], "z": r["loc"][2], "span": r["Span"], "yaw": r["Yaw"],
                            "width": r["Width"]})
    return out


def frame(x, y, z, yaw, pitch):
    """at(a, l, h): the point `a` along the deck, `l` to its left and `h` above it."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))

    def at(a, l, h):
        return (x + a * cp * cy - l * sy - h * sp * cy, y + a * cp * sy + l * cy - h * sp * sy, z + a * sp + h * cp)
    return at


def parts(x, y, z, yaw, pitch, span, width, bed, pier_span):
    at = frame(x, y, z, yaw, pitch)
    rot = (pitch, yaw, 0.0)
    rows = [(at(0.0, 0.0, -27.0), rot, (span / 100.0, (width + 100.0) / 100.0, 0.5), MESH["Cube"])]
    for q in range(int(math.ceil(span / RAIL_CM))):
        for side in (1.0, -1.0):
            rows.append((at(-0.5 * span + RAIL_CM * q, side * (0.5 * width + 40.0), -2.0), rot, (1.0, 1.0, 1.0), MESH["Rail"]))
    for e in (-1.0, 1.0):
        rows.append((at(e * (0.5 * span + 150.0), 0.0, -202.0), (0.0, yaw, 0.0), (3.0, (width + 100.0) / 100.0, 4.0),
                     MESH["Cube"]))
    if span > pier_span and bed is not None:
        h = (z - 52.0) - bed
        if h > 100.0:
            rows.append(((x, y, bed + 0.5 * h), (0.0, 0.0, 0.0), (1.2, 1.2, h / 100.0), MESH["Cylinder"]))
    return rows


def run(inputs, params, ctx):
    up = inputs.get("Upstream", [])
    river = river_rows(up)
    rp = [r[:2] for r in river]
    bridges, rows = [], []
    crossings = 0
    for rd in road_rows(up):
        pts = rd["pts"]
        for x, y, i, t, j, u in geom.polyline_intersections([p[:2] for p in pts], rp) if len(rp) > 1 else []:
            crossings += 1
            a, b = pts[i], pts[i + 1]
            z = a[2] + (b[2] - a[2]) * t
            yaw = geom.yaw_deg(a, b)
            pitch = math.degrees(math.atan2(b[2] - a[2], max(geom.dist2d(a, b), 1e-6)))
            ra, rb = river[j], river[j + 1]
            width = ra[3] + (rb[3] - ra[3]) * u
            bed = ra[4] + (rb[4] - ra[4]) * u
            sin = max(abs(math.sin(math.radians(geom.yaw_deg(ra, rb) - yaw))), 0.25)
            span = min(width / sin + 2.0 * params["EndClearance"], MAX_SPAN)
            rows.extend(parts(x, y, z, yaw, pitch, span, rd["width"], bed, params["PierSpan"]))
            bridges.append({"loc": (x, y, z), "Span": span, "Yaw": yaw, "Width": rd["width"], "RoadId": rd["id"]})
    out = {"Bridges": [], "Parts": [], "Summary": [(WP.summary({
        "bridges": len(bridges), "crossings": crossings, "parts": len(rows),
        "max_span_cm": max((b["Span"] for b in bridges), default=0.0)}), ["Summary"])]}
    if bridges:
        out["Bridges"] = [(WP.table_points(bridges, {"Span": "Double", "Yaw": "Double", "Width": "Double",
                                                      "RoadId": "Int32"}), ["Bridge"])]
        out["Parts"] = [(WP.mesh_points(rows), ["BridgePart"])]
    return out
