"""PyWorld W8 -- props along the roads (视频：最早的工具是电线杆间的电线；道路轨迹复用于电线、旗子).

The road polylines are reused: a power pole every PoleSpacing on the right of every road outside settlements and off
bridges, two wires sagging between consecutive poles (a parabola, a thin box every 2.5 m), guard rails where the
ground just past the road's flattened corridor (16 m beside it) drops or rises more than RailDrop, street lamps along settlement streets and benches
around the plazas."""
import bisect
import math

from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, ROAD_BLEND, ROAD_INNER, geom, points as WP

STAGE = 108
RECORD = "w08"
DOC = """PyWorld W8 Props (沿路道具): power poles and wires along the roads, guard rails on embankments, street
lamps in the settlements and benches round the plazas."""
RANDOM = False
PARAMS = {"PoleSpacing": Param(4000.0, "Distance between power poles (cm)", type="Double"),
          "LampSpacing": Param(3000.0, "Distance between street lamps (cm)", type="Double"),
          "Sag": Param(80.0, "Wire sag at mid span (cm)", type="Double"),
          "RailDrop": Param(150.0, "Height difference beside the road that calls for a rail (cm)", type="Double")}
INPUTS = {"Surface": "surface", "Upstream": "any"}
OUTPUTS = ("Props", "Summary")
POLE_H = 900.0
ARM = 70.0
WIRE_STEP = 250.0
RAIL_CM = 400.0
RAIL_PROBE = ROAD_INNER + ROAD_BLEND + 300.0   # past the corridor W4 flattens, where cut or fill shows


def z_at(pts, cum, s):
    s = min(max(s, 0.0), cum[-1])
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    return pts[i][2] + (pts[i + 1][2] - pts[i][2]) * t, i


def wire(a, b, sag):
    """Thin boxes along a parabola from a to b (3D), one per WIRE_STEP of horizontal length."""
    m = max(1, int(math.ceil(geom.dist2d(a, b) / WIRE_STEP)))
    pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t - 4.0 * sag * t * (1.0 - t))
           for t in (q / m for q in range(m + 1))]
    rows = []
    for p, q in zip(pts, pts[1:]):
        dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        h = math.hypot(dx, dy)
        rows.append((((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2),
                     (math.degrees(math.atan2(dz, h)), math.degrees(math.atan2(dy, dx)), 0.0),
                     (math.hypot(h, dz) / 100.0, 0.03, 0.03), MESH["Cube"]))
    return rows


def run(inputs, params, ctx):
    up = inputs.get("Upstream", [])
    surface = next((v for v, _t in inputs.get("Surface", []) if hasattr(v, "height")), None)
    locs = [(r["loc"][0], r["loc"][1], r["Radius"]) for v in WP.values_tagged(inputs, "Upstream", "Location")
            for r in WP.rows_of(v)]

    def ground(x, y, fallback):
        h = surface.height(x, y) if surface is not None else None
        return h if h is not None else fallback

    def in_town(x, y):
        return any(math.hypot(x - lx, y - ly) < lr for lx, ly, lr in locs)
    rows, poles, wires, rails, spacings = [], 0, 0, 0, []
    for rd in road_rows(up):
        pts = rd["pts"]
        pts2 = [p[:2] for p in pts]
        cum = geom.cumulative(pts2)
        hw = 0.5 * rd["width"]
        near_bridge = lambda i: any(rd["bridge"][q] for q in range(max(0, i - 2), min(len(pts), i + 4)))
        run_, s = [], 0.0

        def flush():
            nonlocal wires
            for (pa, na), (pb, nb) in zip(run_, run_[1:]):
                spacings.append(geom.dist2d(pa, pb))
                for side in (1.0, -1.0):
                    w = wire((pa[0] + na[0] * side * ARM, pa[1] + na[1] * side * ARM, pa[2]),
                             (pb[0] + nb[0] * side * ARM, pb[1] + nb[1] * side * ARM, pb[2]), params["Sag"])
                    rows.extend(w)
                    wires += len(w)
            run_.clear()
        while s <= cum[-1] + 1e-6:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            zr, i = z_at(pts, cum, s)
            if near_bridge(i) or in_town(x, y):
                flush()
                s += params["PoleSpacing"]
                continue
            nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
            px, py = x - nx * (hw + 250.0), y - ny * (hw + 250.0)
            z0 = ground(px, py, zr)
            rows.append(((px, py, z0 + 0.5 * POLE_H - 30.0), (0.0, 0.0, 0.0), (0.28, 0.28, POLE_H / 100.0), MESH["Cylinder"]))
            rows.append(((px, py, z0 + POLE_H - 70.0), (0.0, yaw + 90.0, 0.0), (1.6, 0.12, 0.12), MESH["Cube"]))
            run_.append(((px, py, z0 + POLE_H - 60.0), (nx, ny)))
            poles += 1
            s += params["PoleSpacing"]
        flush()
        s = 0.0
        while s <= cum[-1]:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            zr, i = z_at(pts, cum, s)
            if not near_bridge(i) and not in_town(x, y):
                nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
                pitch = math.degrees(math.atan2(pts[i + 1][2] - pts[i][2], max(cum[i + 1] - cum[i], 1e-6)))
                for side in (1.0, -1.0):
                    g = ground(x + nx * side * (hw + RAIL_PROBE), y + ny * side * (hw + RAIL_PROBE), zr)
                    if abs(g - zr) > params["RailDrop"]:
                        rows.append(((x + nx * side * (hw + 50.0), y + ny * side * (hw + 50.0), zr), (pitch, yaw, 0.0),
                                     (1.0, 1.0, 1.0), MESH["Rail"]))
                        rails += 1
            s += RAIL_CM
    lamps = 0
    for v, tags in up:
        if not (isinstance(v, Points) and "Street" in tags and len(v) > 1):
            continue
        st = sorted(WP.rows_of(v), key=lambda r: r["S"])
        pts2 = [r["loc"][:2] for r in st]
        cum = geom.cumulative(pts2)
        hw = 0.5 * st[0]["Width"]
        s, side = 0.0, 1.0
        while s <= cum[-1] + 1e-6:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            nx, ny = -math.sin(math.radians(yaw)) * side, math.cos(math.radians(yaw)) * side
            lx, ly = x + nx * (hw + 80.0), y + ny * (hw + 80.0)
            rows.append(((lx, ly, ground(lx, ly, st[0]["loc"][2])), (0.0, yaw - 90.0 * side, 0.0), (1.0, 1.0, 1.0), MESH["Lamp"]))
            lamps += 1
            s += params["LampSpacing"]
            side = -side
    benches = 0
    for v, tags in up:
        if isinstance(v, Polygon) and "Plaza" in tags:
            cx, cy = geom.centroid(v.outer)
            rad = sum(geom.dist2d((cx, cy), p) for p in v.outer) / len(v.outer) - 250.0
            for q in range(6):
                a = 60.0 * q
                bx, by = cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a))
                rows.append(((bx, by, ground(bx, by, v.z)), (0.0, a + 90.0, 0.0), (1.0, 1.0, 1.0), MESH["Bench"]))
                benches += 1
    summary = {"poles": poles, "wire_segments": wires, "lamps": lamps, "rails": rails, "benches": benches,
               "pole_spacing_mean_m": (sum(spacings) / len(spacings) / 100.0) if spacings else 0.0}
    return {"Props": [(WP.mesh_points(rows), ["Prop"])] if rows else [], "Summary": [(WP.summary(summary), ["Summary"])]}
