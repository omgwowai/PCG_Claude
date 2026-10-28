"""Run the PyWorld stages W3 -> W4 -> W5 -> W6 offline on the editor's own data, draw a top-down plan and measure the
shapes of the river, the roads and the streets.

The inputs come from a capture (`pyworld.py gen {"stage": 3, "capture": true}` writes Saved/PyPCG/captures/w03.pkl:
the terrain W3 reads, after W1 and the erosion, and W2's outputs). Each later stage gets what its graph wires to it
(pypcg/world/graphs.py): the previous terrain writer's Terrain output and the Output-node items of the upstream volumes.

    C:\\Python314\\python.exe Tools/pyworld/offline.py --tag before [--stages 3,4,5,6]

writes Saved/Reports/pyworld_plan_<tag>.png (north up, 1 px = PX_CM) and Saved/Reports/pyworld_shape_<tag>.json."""
import argparse
import json
import math
import os
import pickle
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import stage_api  # noqa: E402
from pypcg.geo import Points, Polygon  # noqa: E402
from pypcg.stages import w03_river, w04_roads, w05_bridges, w06_settlements  # noqa: E402
from pypcg.world import geom, shape, VERTEX_CM  # noqa: E402
from pypcg.world.grid import Lattice  # noqa: E402

REPORTS = os.path.join(REPO, "Saved", "Reports")
# graph Output-node pins per stage (graphs.py g.out(...)): what a downstream Get_ActorData sees
OUT_PINS = {3: ("River", "Summary"), 4: ("Roads", "Summary"), 5: ("Bridges", "Summary"),
            6: ("Buildings", "Streets", "Areas", "Summary")}


def run(module, inputs, params=None):
    p = stage_api.defaults(module)
    p.update(params or {})
    for pin in module.INPUTS:
        inputs.setdefault(pin, [])
    t0 = time.perf_counter()
    out, ctx = stage_api.execute(module, inputs, p, None)
    return out, ctx, time.perf_counter() - t0


def published(n, out):
    return [(v, frozenset(t)) for pin in OUT_PINS[n] for v, t in out.get(pin, [])]


def chain(stages=(3, 4, 5, 6), params=None):
    """{n: outputs} of the stages run in order on the w03 capture."""
    params = params or {}
    inputs, _p = stage_api.load_capture("w03")
    w2 = inputs["Upstream"]
    res, times = {}, {}
    terrain = inputs["Terrain"]
    if 3 in stages:
        res[3], ctx, times[3] = run(w03_river, {"Terrain": terrain, "Upstream": list(w2)}, params.get(3))
        terrain = [(v, frozenset(t)) for v, t in res[3]["Terrain"]]
    if 4 in stages:
        res[4], ctx, times[4] = run(w04_roads, {"Terrain": terrain, "Upstream": w2 + published(3, res[3])},
                                    params.get(4))
        terrain = [(v, frozenset(t)) for v, t in res[4]["Terrain"]]
    if 5 in stages:
        res[5], ctx, times[5] = run(w05_bridges, {"Upstream": published(3, res[3]) + published(4, res[4])},
                                    params.get(5))
    if 6 in stages:
        res[6], ctx, times[6] = run(w06_settlements, {"Terrain": terrain, "Upstream": w2 + published(3, res[3])
                                                      + published(4, res[4])}, params.get(6))
        terrain = [(v, frozenset(t)) for v, t in res[6]["Terrain"]]
    return res, terrain, times, w2


# ---- shape metrics ------------------------------------------------------------------------------------------------
def line_stats(pts):
    return {k: round(v, 3) for k, v in shape.stats(pts).items()}


def angular_spacing(streets, cx, cy):
    """Coefficient of variation of the gaps between the bearings at which streets leave a settlement centre: 0 for
    evenly spaced spokes."""
    bs = sorted(math.degrees(math.atan2(s[min(3, len(s) - 1)][1] - cy, s[min(3, len(s) - 1)][0] - cx)) % 360.0
                for s in streets)
    if len(bs) < 3:
        return None
    gaps = [(bs[(i + 1) % len(bs)] - bs[i]) % 360.0 for i in range(len(bs))]
    m = sum(gaps) / len(gaps)
    return round(math.sqrt(sum((g - m) ** 2 for g in gaps) / len(gaps)) / m, 3)


def measure(res, w2):
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    out = {}
    if 3 in res:
        rr = river_rows(res[3]["River"])
        out["river"] = line_stats([r[:2] for r in rr])
        ws = [r[3] for r in rr]
        out["river"]["width_cv"] = round(_cv(_detrend(ws)), 3) if ws else 0.0
        out["river_summary"] = res[3]["Summary"][0][0].values
    if 4 in res:
        roads = road_rows(res[4]["Roads"])
        out["roads"] = [dict(line_stats(rd["pts"]), cls=rd["cls"]) for rd in roads]
        out["roads_summary"] = res[4]["Summary"][0][0].values
    if 6 in res:
        streets = [[p[:2] for p in v.loc] for v, t in res[6]["Streets"]]
        out["streets"] = {"n": len(streets), "length_m": round(sum(geom.length(s) for s in streets) / 100.0, 1),
                          "straight_share": round(sum(sum(shape.straight_runs(s)) for s in streets)
                                                  / max(1.0, sum(geom.length(s) for s in streets)), 3)}
        locs = [r for v, t in w2 if "Location" in t for r in _rows(v)]
        out["spacing_cv"] = {}
        for r in locs:
            cx, cy, rad = r["loc"][0], r["loc"][1], r["Radius"]
            near = [s for s in streets if math.hypot(s[0][0] - cx, s[0][1] - cy) < 0.5 * rad]
            out["spacing_cv"][r["Kind"] + str(r["Id"])] = angular_spacing(near, cx, cy)
        out["settlements_summary"] = res[6]["Summary"][0][0].values
    return out


def _rows(v):
    from pypcg.world import points as WP
    return WP.rows_of(v)


def _detrend(vals, half=20):
    sm = geom.moving_average(vals, half)
    return [v / s for v, s in zip(vals, sm)]


def _cv(vals):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) / m if m else 0.0


# ---- drawing ------------------------------------------------------------------------------------------------------
PX_CM = 130.0                    # 1.3 m per pixel
BOX = (-110000.0, -140000.0, 110000.0, 105000.0)     # x0, y0, x1, y1 (cm): the floor, the river, the settlements


def draw(res, terrain, w2, path):
    from PIL import Image, ImageDraw
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    x0, y0, x1, y1 = BOX
    W, H = int((x1 - x0) / PX_CM), int((y1 - y0) / PX_CM)
    locs = [p for v, _t in terrain if isinstance(v, Points) for p in v.loc]
    lat, _ks = Lattice.from_locs(locs, VERTEX_CM)
    img = Image.new("RGB", (W, H))
    pix = img.load()
    # hillshade + height tint, sampled per pixel from the lattice (bilinear)
    for py in range(H):
        y = y1 - (py + 0.5) * PX_CM
        for px in range(W):
            x = x0 + (px + 0.5) * PX_CM
            s = lat.surface(x, y)
            if s is None:
                continue
            z, gx, gy = s
            nx, ny, nz = -gx, -gy, 1.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            shade = max(0.0, (-0.5 * nx + 0.5 * ny + 0.7 * nz) / (ln * 0.9899))
            t = min(1.0, max(0.0, (z + 600.0) / 20000.0))
            base = (int(150 + 60 * t), int(170 + 40 * t), int(120 + 50 * t))
            pix[px, py] = tuple(int(c * (0.35 + 0.65 * shade)) for c in base)
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((x - x0) / PX_CM, (y1 - y) / PX_CM)
    if 6 in res:
        for v, t in res[6]["Areas"]:
            if isinstance(v, Polygon) and "Field" in t:
                d.polygon([P(*q) for q in v.outer], fill=(196, 170, 110))
    if 3 in res:
        rr = river_rows(res[3]["River"])
        left, right = [], []
        for i, r in enumerate(rr):
            a, b = rr[max(0, i - 1)], rr[min(len(rr) - 1, i + 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            h = 0.5 * r[3]
            left.append(P(r[0] + nx * h, r[1] + ny * h))
            right.append(P(r[0] - nx * h, r[1] - ny * h))
        if len(rr) > 1:
            d.polygon(left + right[::-1], fill=(40, 90, 150))
    if 4 in res:
        for rd in road_rows(res[4]["Roads"]):
            wpx = max(1, int(round(rd["width"] / PX_CM)))
            d.line([P(p[0], p[1]) for p in rd["pts"]], fill=(90, 80, 70) if rd["cls"] == "Main" else (120, 105, 85),
                   width=wpx, joint="curve")
    if 6 in res:
        for v, t in res[6]["Streets"]:
            d.line([P(p[0], p[1]) for p in v.loc], fill=(150, 130, 100), width=max(1, int(400.0 / PX_CM)), joint="curve")
        styles = iter(building_styles(res[6]))
        for v, t in res[6]["Areas"]:
            if isinstance(v, Polygon) and "Footprint" in t:
                d.polygon([P(*q) for q in v.outer], fill=STYLE_RGB.get(next(styles, None), (170, 60, 50)))
            elif isinstance(v, Polygon) and "Plaza" in t:
                d.polygon([P(*q) for q in v.outer], outline=(220, 220, 220))
    if 5 in res:
        from pypcg.stages.w05_bridges import bridge_rows
        for b in bridge_rows(res[5]["Bridges"]):
            ring = geom.rect(b["x"], b["y"], b["span"], b["width"] + 200.0, b["yaw"])
            d.polygon([P(*q) for q in ring], fill=(230, 230, 230))
    img.save(path)
    return W, H


# the style codes of pypcg/world/bdf.py on the plans: limestone pale, plaster in its colours, brick red
STYLE_RGB = {"LSA": (240, 232, 210), "LSB": (205, 196, 172), "PLA": (232, 188, 105), "PLB": (165, 205, 145),
             "PLC": (160, 182, 225), "BRA": (195, 85, 55), "BRB": (135, 55, 40)}


def building_styles(out6):
    """W6's buildings' style codes, in the order of their Footprint areas (both written per building)."""
    from pypcg.world import points as WP
    return [r["Style"] for v, _t in out6.get("Buildings", []) for r in WP.rows_of(v)]


def draw_town(res, path, centre, half=26000.0, px_cm=40.0):
    """A close plan of one settlement: roads, streets, the plaza and every footprint in its style's colour; buildings
    sharing a wall (terraces) outlined dark, landmarks white; a legend of the style codes."""
    from PIL import Image, ImageDraw
    from pypcg.stages.w04_roads import road_rows
    from pypcg.world import points as WP
    cx, cy = centre
    W = H = int(2 * half / px_cm)
    img = Image.new("RGB", (W, H), (214, 216, 200))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((x - cx + half) / px_cm, (cy + half - y) / px_cm)
    for rd in road_rows(res[4]["Roads"]):
        d.line([P(p[0], p[1]) for p in rd["pts"]], fill=(95, 90, 82), width=max(1, int(rd["width"] / px_cm)),
               joint="curve")
    for v, _t in res[6]["Streets"]:
        d.line([P(p[0], p[1]) for p in v.loc], fill=(176, 160, 128), width=max(1, int(400.0 / px_cm)), joint="curve")
    rows = [r for v, _t in res[6]["Buildings"] for r in WP.rows_of(v)]
    rings = [v.outer for v, t in res[6]["Areas"] if isinstance(v, Polygon) and "Footprint" in t]
    idx = geom.RingIndex()
    for rg in rings:
        idx.add(rg)
    for v, t in res[6]["Areas"]:
        if isinstance(v, Polygon) and "Plaza" in t:
            d.polygon([P(*q) for q in v.outer], fill=(200, 196, 184), outline=(120, 120, 120))
        elif isinstance(v, Polygon) and "Field" in t:
            d.polygon([P(*q) for q in v.outer], fill=(200, 180, 120))
    for i, (rg, r) in enumerate(zip(rings, rows)):
        landmark = r["Kind"] in ("Church", "TownHall", "BellTower")
        outline = (255, 255, 255) if landmark else ((30, 30, 30) if idx.touching(i, 20.0) else None)
        d.polygon([P(*q) for q in rg], fill=STYLE_RGB.get(r["Style"], (170, 60, 50)), outline=outline)
    y = 10
    for code, rgb in STYLE_RGB.items():
        d.rectangle([10, y, 34, y + 18], fill=rgb, outline=(0, 0, 0))
        d.text((42, y + 3), code, fill=(0, 0, 0))
        y += 24
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="now")
    ap.add_argument("--stages", default="3,4,5,6")
    ap.add_argument("--nodraw", action="store_true")
    ap.add_argument("--town", action="store_true", help="also a close plan of the largest settlement by style")
    a = ap.parse_args()
    stages = tuple(int(s) for s in a.stages.split(","))
    res, terrain, times, w2 = chain(stages)
    m = measure(res, w2)
    m["seconds"] = {k: round(v, 2) for k, v in times.items()}
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "pyworld_shape_%s.json" % a.tag), "w") as fh:
        json.dump(m, fh, indent=1, default=str)
    with open(os.path.join(REPORTS, "pyworld_chain_%s.pkl" % a.tag), "wb") as fh:
        pickle.dump({n: {pin: [(v, list(t)) for v, t in items] for pin, items in out.items() if pin != "Terrain"}
                     for n, out in res.items()}, fh, protocol=4)
    if not a.nodraw:
        draw(res, terrain, w2, os.path.join(REPORTS, "pyworld_plan_%s.png" % a.tag))
    if a.town and 6 in res:
        from pypcg.world import points as WP
        locs = [r for v, t in w2 if "Location" in t for r in WP.rows_of(v)]
        big = max(locs, key=lambda r: r["Radius"])
        draw_town(res, os.path.join(REPORTS, "pyworld_town_%s.png" % a.tag), big["loc"][:2])
    print(json.dumps(m, indent=1, default=str))


if __name__ == "__main__":
    main()
