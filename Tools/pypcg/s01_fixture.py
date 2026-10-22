"""Distil the stage-1 taps into `Tools/pypcg/data/s01_fixture.json` (the offline tests' official numbers).

Inputs (written 2026-10-20 by the editor probes, on the demo level; the official graph ran as a TAP graph on a
SPAWNED probe actor with the stage-1 volume's transform -- (0, 0, 0), scale (25, 25, 10), component
seed 42, CityFlatness 0.6000000238418579 -- so the stage-1 volume and its terrain write were never touched):
  Saved/t24/tap_a.json            `pypcg_s01_taps.py {"variant": "official"}` + its read: t01 .. t16
  Saved/t24/tap_extract_full.json the same t01 read with every point field (a fuller read of the same tap)
  Saved/t24/extract_200000.json   Step A+, the 2 km box (`bound` 200000); an earlier extract probe wrote it
Run: `C:/Python314/python.exe Tools/pypcg/s01_fixture.py`.

What it keeps (every array is a slice of an official tap, never recomputed here):
  step_a_plus  the 2 km box: points, area, points per m2, the convert timings; and the stage's own count
  extract      the extracted points on the four edge rows (the only ones that can reach the bounds), their point
               fields (one value each on the demo), the count and the bounding box
  footprint    t04 (Trace_Bound_Footprint, Top), t05 (expanded 600 m), t06 (offset down): rings, z, frames
  circle       t07 (Terrain_shaping_1 as read) and t08 (offset down): control points, tangents, polyline
  annulus      t09 (square minus circle): outer, the hole, z, frame
  city         t11 (as read), t12 (Z set to 0), t13 (moved up 3000): control points, tangents, frame
  ratio        t15 (OneMinus of CityFlatness)
  sample       400 points (fixed indices): their extract position, hills (t02), flattened (t10), city-projected
               (t14) and final (t16) positions and SourcePositions -- the Lerp's official inputs and output
  stats        per-tap counts and z ranges, and the city / outer-ring numbers the invariants use
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(REPO, "Content", "Python")]

from pypcg import geo  # noqa: E402

T24 = os.path.join(REPO, "Saved", "t24")
OUT = os.path.join(HERE, "data", "s01_fixture.json")
SAMPLE = 400


def _load(name):
    with open(os.path.join(T24, name), encoding="utf-8") as fh:
        return json.load(fh)


def _spline(x):
    return {k: x[k] for k in ("points", "closed", "linear", "tangents", "polyline", "frame") if k in x}


def _poly(x):
    return {k: x[k] for k in ("outer", "holes", "z", "frame", "vertices") if k in x}


def _inside(ring, x, y):
    c = False
    n = len(ring)
    for i in range(n):
        (x0, y0), (x1, y1) = ring[i][:2], ring[(i + 1) % n][:2]
        if (y0 <= y) != (y1 <= y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def main():
    tap = _load("tap_a.json")
    full = _load("tap_extract_full.json")["t01_extract"][0]
    a_plus = _load("extract_200000.json")
    loc = {k: tap[k][0]["loc"] for k in ("t01_extract", "t02_noise", "t10_flat_annulus", "t14_city_proj", "t16_lerp")}
    n = len(loc["t01_extract"])
    xs = [p[0] for p in loc["t01_extract"]]
    ys = [p[1] for p in loc["t01_extract"]]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    edge = [i for i, p in enumerate(loc["t01_extract"]) if p[0] in (lo_x, hi_x) or p[1] in (lo_y, hi_y)]
    fields = {}
    for c in ("rot", "scale", "bounds_min", "bounds_max", "color", "density", "steepness"):
        vals = {json.dumps(v) for v in full[c]}
        fields[c] = [json.loads(v) for v in sorted(vals)]
    idx = sorted(random.Random(1).sample(range(n), SAMPLE))
    sp = tap["t16_lerp"][0]["attrs"]["SourcePositions"]
    city_ring = tap["t13_city_up"][0]["polyline"]
    final = loc["t16_lerp"]
    inside = [i for i in range(n) if _inside(city_ring, final[i][0], final[i][1])]
    zin = [final[i][2] for i in inside]
    hills_in = [loc["t10_flat_annulus"][i][2] for i in inside]
    flat_in = [loc["t14_city_proj"][i][2] for i in inside]
    core = [p[2] for p in final if (p[0] ** 2 + p[1] ** 2) ** 0.5 < 50000.0]
    ring = [p[2] for p in final if (p[0] ** 2 + p[1] ** 2) ** 0.5 > 140000.0]
    out = {
        "source": "official PCG_1_1_Terrain as a tap graph on a probe actor with the stage-1 volume's transform, "
                  "component seed 42, CityFlatness 0.6000000238418579, HillsHeight 7001 (2026-10-20)",
        "step_a_plus": {"bound_cm": 200000, "points": a_plus["points"], "area_m2": a_plus["area_m2"],
                        "points_per_m2": a_plus["points_per_m2"], "grid": [a_plus["distinct_x"], a_plus["distinct_y"]],
                        "spacing_cm": (a_plus["bbox_m"][1][0] - a_plus["bbox_m"][0][0]) * 100.0 / (a_plus["distinct_x"] - 1),
                        "seconds": a_plus["seconds"], "us_per_point": a_plus["us_per_point"],
                        "stage_points": n},
        "extract": {"n": n, "bbox": [[lo_x, lo_y], [hi_x, hi_y]], "z": sorted({p[2] for p in loc["t01_extract"]}),
                    "edge": [loc["t01_extract"][i] for i in edge], "fields": fields},
        "footprint": {"t03_bounds": tap["t03_bounds"][0]["loc"], "t04": _spline(tap["t04_footprint"][0]),
                      "t05": _poly(tap["t05_expand"][0]), "t06": _poly(tap["t06_square"][0])},
        "circle": {"t07": _spline(tap["t07_circle_raw"][0]), "t08": _spline(tap["t08_circle"][0])},
        "annulus": _poly(tap["t09_annulus"][0]),
        "city": {"t11": _spline(tap["t11_city_raw"][0]), "t12": _spline(tap["t12_city_z0"][0]),
                 "t13": _spline(tap["t13_city_up"][0])},
        "ratio": tap["t15_ratio"][0]["values"],
        "sample": {"index": idx, "extract": [loc["t01_extract"][i] for i in idx],
                   "hills": [loc["t02_noise"][i] for i in idx], "flat": [loc["t10_flat_annulus"][i] for i in idx],
                   "city": [loc["t14_city_proj"][i] for i in idx], "final": [final[i] for i in idx],
                   "source_positions": [sp[i] for i in idx]},
        "stats": {"counts": {k: len(v) for k, v in loc.items()},
                  "z_range": {k: [min(p[2] for p in v), max(p[2] for p in v)] for k, v in loc.items()},
                  "city_inside": len(inside), "city_z": [min(zin), max(zin), sum(zin) / len(zin)],
                  "city_hills_z": [min(hills_in), max(hills_in), sum(hills_in) / len(hills_in)],
                  "city_flat_z": [min(flat_in), max(flat_in), sum(flat_in) / len(flat_in)],
                  "core_mean_z": sum(core) / len(core), "core_n": len(core),
                  "outer_ring_mean_z": sum(ring) / len(ring), "outer_ring_n": len(ring),
                  "annulus_area_m2": geo.area_m2(geo.Polygon([tuple(p) for p in tap["t09_annulus"][0]["outer"]],
                                                             [[tuple(p) for p in h] for h in tap["t09_annulus"][0]["holes"]]))},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print("wrote", OUT, "edge", len(edge), "inside city", len(inside))


if __name__ == "__main__":
    main()
