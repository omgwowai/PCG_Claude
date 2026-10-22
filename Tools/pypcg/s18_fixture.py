"""Distil the stage-18 taps into `Tools/pypcg/data/s18_fixture.json` (the offline tests' official numbers).

Inputs (written by the untracked editor probe `Content/Python/pyg_probe_t23_tap.py`, 2026-10-20, component
seed 42, on the demo level's stage-18 volume):
  Saved/t23/tapA.json        the official graph: t01 (terrain points) .. t17
  Saved/t23/B/uNN_*.json     the official graph with the substitute texture on both writes (split from
                             Saved/t23/tapB_counts.json): u01 .. u19
Run: `C:/Python314/python.exe Tools/pypcg/s18_fixture.py`.

What it keeps (every array is a slice of an official tap, never recomputed here):
  footprint   the terrain points whose own boxes reach the six extremes (each at most a few), the official
              four corners and the official Extract_Bounds point
  areas       the official area pieces' sizes and the scatter's sizes (for the count invariant)
  index       160 points before (u04) and after (u05) the normalisation, with the official min and max
  water       160 projected points (u06) and their side of the split
  shore       100 sources in one 200 m window (u06) with their official shore weight (u09), every above-water
              target (u07) within 50 m of them, and the global min / max the remap used
  deep        the same for the deep-forest weight: 100 near-shore sources (u11), u12, the below-water targets (u08)
  floor       200 densities before (u13) and after (u14) the scale floor, with the scale before (u14) and after (u15)
  assign      300 points of u16 (index) with the official Asset (u17), and u17's per-mesh counts
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(REPO, "Content", "Python")]

from pypcg import geo  # noqa: E402
from pypcg.stages import s18_outer_forest as S  # noqa: E402

T23 = os.path.join(REPO, "Saved", "t23")
OUT = os.path.join(HERE, "data", "s18_fixture.json")


def _b(k):
    return json.load(open(os.path.join(T23, "B", k + ".json"), encoding="utf-8"))


def _pick(n, k):
    """k indices spread evenly over range(n)."""
    if n <= k:
        return list(range(n))
    return [int(i * n / k) for i in range(k)]


def footprint_part(a):
    t = a["t01_terrain_points"][0]
    p = geo.Points()
    for c in ("loc", "rot", "scale", "bounds_min", "bounds_max"):
        setattr(p, c, [tuple(x) for x in t[c]])
    n = len(p.loc)
    for c in ("density", "color", "steepness", "seed"):
        setattr(p, c, [geo.Points.DEFAULTS[c]] * n)
    p.quat = [tuple(q) for q in t["quat"]]
    boxes = [S._world_box(p, i) for i in range(n)]
    keep = set()
    for k in range(3):
        lo = min(b[0][k] for b in boxes)
        hi = max(b[1][k] for b in boxes)
        keep |= {i for i, b in enumerate(boxes) if b[0][k] == lo or b[1][k] == hi}
    keep = sorted(keep)
    pts = {c: [list(getattr(p, c)[i]) for i in keep] for c in ("loc", "rot", "scale", "bounds_min", "bounds_max")}
    pts["quat"] = [list(p.quat[i]) for i in keep]
    return {"points": pts, "of": n, "corners": a["t03_footprint"][0]["points"],
            "bounds": {k: a["t02_bounds"][0][k] for k in ("loc", "bounds_min", "bounds_max")}}


def window(sets, centre, half):
    out = []
    for si, s in enumerate(sets):
        for j, p in enumerate(s["loc"]):
            if abs(p[0] - centre[0]) <= half and abs(p[1] - centre[1]) <= half:
                out.append((si, j))
    return out


def distance_part(src_sets, src_vals, tgt_sets, reach, k=100, half=10000.0):
    """k sources from a window around the first source that sees both a land and a sea point, their official
    values, and every target within `reach` of any of them (with the scale and box the centre uses)."""
    flat_t = [(si, j) for si, s in enumerate(tgt_sets) for j in range(len(s["loc"]))]
    # a window where the official value varies: around the median-valued source
    vals = [(v, si, j) for si, vs in enumerate(src_vals) for j, v in enumerate(vs) if 0.0 < v < 1.0]
    vals.sort()
    _v, si0, j0 = vals[len(vals) // 2]
    c = src_sets[si0]["loc"][j0]
    cand = window(src_sets, c, half)
    picks = [cand[i] for i in _pick(len(cand), k)]
    sources = [{"loc": src_sets[si]["loc"][j], "value": src_vals[si][j]} for si, j in picks]
    targets = []
    for si, j in flat_t:
        q = tgt_sets[si]["loc"][j]
        if any(math.hypot(q[0] - s["loc"][0], q[1] - s["loc"][1]) < reach + 50.0 for s in sources):
            targets.append({"loc": q, "scale": tgt_sets[si]["scale"][j], "bounds_min": tgt_sets[si]["bounds_min"][j],
                            "bounds_max": tgt_sets[si]["bounds_max"][j]})
    allv = [v for vs in src_vals for v in vs]
    # The remap's input range is the RAW range (distance / MaximumDistance over every source), which the official
    # values do not carry. Measured with the full official sets (s18.md 6): 0.0 (a source exactly on a target's
    # centre) and 1.0 (a source out of reach), for both weights; the official values reach both ends.
    return {"sources": sources, "targets": targets, "official_min": min(allv), "official_max": max(allv),
            "raw_range": [0.0, 1.0]}


def main():
    a = json.load(open(os.path.join(T23, "tapA.json"), encoding="utf-8"))
    fx = {"footprint": footprint_part(a)}
    fx["areas"] = {"official_m2": [geo.area_m2(geo.Polygon([tuple(q) for q in P["outer"]],
                                                             [[tuple(q) for q in h] for h in P["holes"]]))
                                   for P in a["t11_forest_area"]],
                   "scatter": [x["n"] for x in a["t12_scatter"]], "tree_density": 0.05,
                   "artery": a["t16_artery"][0]["values"]["ArteryWidth"],
                   "city_expand": a["t05_city_expand"][0]["values"]["ArteryWidth"]}
    del a
    u04, u05 = _b("u04_index_jitter"), _b("u05_index_norm")
    idx = []
    for si, (x, y) in enumerate(zip(u04, u05)):
        for j in _pick(len(x["loc"]), 40):
            idx.append([si, x["attrs"]["index"][j], y["attrs"]["index"][j]])
    fx["index"] = {"min": _b("u18_index_min")[0]["values"]["None"], "max": _b("u19_index_max")[0]["values"]["None"],
                   "points": idx, "u03_range": None}
    u03 = _b("u03_tex_index")
    allv = [v for x in u03 for v in x["attrs"]["index"]]
    fx["index"]["u03_range"] = [min(allv), max(allv)]
    jit = [b - c for x, y in zip(u03, u04) for c, b in zip(x["attrs"]["index"], y["attrs"]["index"])]
    fx["index"]["jitter_range"] = [min(jit), max(jit)]
    del u03, u04, u05
    u06, u07, u08 = _b("u06_projected"), _b("u07_above"), _b("u08_below")
    fx["water"] = {"points": [[u06[si]["loc"][j], u06[si]["loc"][j][2] > 0.0]
                              for si in range(len(u06)) for j in _pick(len(u06[si]["loc"]), 40)],
                   "above": [len(x["loc"]) for x in u07], "below": [len(x["loc"]) for x in u08]}
    u09 = _b("u09_shore")
    fx["shore"] = distance_part(u06, [x["attrs"]["distance"] for x in u09], u07, 5000.0)
    del u09
    u10, u11, u12 = _b("u10_shore_noise"), _b("u11_near_shore"), _b("u12_deep")
    noise = [d - geo.frames.f32(v) for x, y in zip(_b("u09_shore"), u10)
             for v, d in zip(x["attrs"]["distance"], y["density"]) if 0.0 < d < 1.0]
    fx["shore"]["noise_range"] = [min(noise), max(noise)]
    fx["shore"]["kept"] = [len(x["loc"]) for x in u11]
    fx["shore"]["densities"] = [[u10[si]["density"][j]] for si in range(len(u10)) for j in _pick(len(u10[si]["loc"]), 50)]
    fx["deep"] = distance_part(u11, [x["attrs"]["distance"] for x in u12], u08, 10000.0)
    del u06, u07, u08, u10
    u13, u14, u15, u16 = _b("u13_deep_noise"), _b("u14_scale_floor"), _b("u15_scaled"), _b("u16_above_cut")
    fl = []
    for si in range(len(u13)):
        for j in _pick(len(u13[si]["loc"]), 50):
            fl.append([u13[si]["density"][j], u14[si]["density"][j], u14[si]["scale"][j], u15[si]["scale"][j]])
    fx["floor"] = fl
    fx["cut"] = {"before": [len(x["loc"]) for x in u15], "after": [len(x["loc"]) for x in u16]}
    u17 = _b("u17_assigned")[0]
    flat = [(si, j) for si in range(len(u16)) for j in range(len(u16[si]["loc"]))]
    picks = _pick(len(flat), 300)
    fx["assign"] = {"points": [[u16[flat[k][0]]["attrs"]["index"][flat[k][1]], u17["attrs"]["Asset"][k]] for k in picks],
                    "per_mesh": {}, "n": len(u17["loc"]),
                    "scale_range": [min(s[0] for s in u17["scale"]), max(s[0] for s in u17["scale"])],
                    "pitch_roll_max": max(max(abs(r[0]), abs(r[2])) for r in u17["rot"])}
    for p in u17["attrs"]["Asset"]:
        fx["assign"]["per_mesh"][p] = fx["assign"]["per_mesh"].get(p, 0) + 1
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(fx, fh, indent=0)
    print("wrote", OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
