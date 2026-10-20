"""Stage 1, Step A+ and Step F, measured offline on the official taps: why three computation nodes stay native.

Inputs: `Saved/t24/tap_a.json` (the official taps, see `s01_fixture.py`). Needs numpy (only this measurement does;
no stage or test imports it). Run: `C:/Python314/python.exe Tools/pypcg/s01_measure_offline.py`.
Writes `Tools/pypcg/data/s01_native_measurements.json`:

  blur      `SpatialNoise_Hills`' inner `BlurElement_1` (`NoiseBlurDistance` 12000 cm, 2 iterations) done the plain way
            in Python -- a 12000 cm bucket hash, every neighbour within the sphere summed -- timed on 2000 of the
            stage's points: microseconds per point, neighbours per point, and the two iterations over every point
  project   `FlattenProject_AroundCircle` (`Transform_Project` onto the square-minus-circle polygon, falloff 0..50000)
            emulated: the polygon's surface-sampler grid (0.5 points per m2: cell sqrt(2e4) cm, offset (cell-0.002)/2,
            ratio 1), the nearest target per point in float32 the way the primitive's `CustomHLSL_1` measures it
            (2D `distance`), the two remaps (`AttributeRemap_4` in double into a float, `AttributeRemap_3`'s
            cubic key as `FRichCurve`'s float Bezier) and the double Lerp. Counted: how many of the 261 312 heights
            come out bit for bit, and by how many float32 ulps the GPU's distance differs where they do not. Timed:
            a pure-Python nearest-target search (double distances only, so a lower bound) on 3000 points
  lerp      `AttributeMathsOp_0`: `A + (B - A) * Ratio` per component against every official component
"""
import json
import math
import os
import random
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
T24 = os.path.join(REPO, "Saved", "t24")
OUT = os.path.join(HERE, "data", "s01_native_measurements.json")
f32 = np.float32


def _band(hole, c, o):
    """Grid nodes OUTSIDE the hole with a 4-neighbour inside it: the only targets a point in the hole can have
    as its nearest (the annulus' other targets are farther than one of these)."""
    hx, hy = hole[:, 0], hole[:, 1]
    nx, ny = np.roll(hx, -1), np.roll(hy, -1)

    def crossings(y):
        m = ((hy <= y) & (ny > y)) | ((ny <= y) & (hy > y))
        return np.sort(hx[m] + (y - hy[m]) * (nx[m] - hx[m]) / (ny[m] - hy[m]))
    lo, hi = math.floor((hy.min() - o) / c) - 2, math.ceil((hy.max() - o) / c) + 2
    rows = {j: crossings(j * c + o) for j in range(lo - 1, hi + 2)}

    def ins(xs, i):
        return (np.searchsorted(xs, i * c + o, side="right") % 2) == 1
    out = []
    for j in range(lo, hi + 1):
        xs = np.concatenate([rows[j - 1], rows[j], rows[j + 1]])
        if not len(xs):
            continue
        i = np.arange(math.floor((xs.min() - o) / c) - 2, math.ceil((xs.max() - o) / c) + 3)
        a = ins(rows[j], i)
        sel = (~a) & (ins(rows[j + 1], i) | ins(rows[j - 1], i) | ins(rows[j], i - 1) | ins(rows[j], i + 1))
        out += [(k * c + o, j * c + o) for k in i[sel]]
    return np.array(out), (lambda x, y: (np.sum(crossings(y) < x) % 2) == 1)


def _mask(d, end):
    r = (np.float64(-1.0 / end) * d.astype(np.float64) + 1.0).astype(f32)
    a = np.clip(r, f32(0), f32(1))

    def lerp(p, q, t):
        return (p + t * (q - p)).astype(f32)
    p01, p12, p23 = lerp(f32(0), f32(0), a), lerp(f32(0), f32(1), a), lerp(f32(1), f32(1), a)
    return lerp(lerp(p01, p12, a), lerp(p12, p23, a), a)


def project(tap):
    an = tap["t09_annulus"][0]
    hole = np.array(an["holes"][0])
    hills = np.array(tap["t02_noise"][0]["loc"])
    flat = np.array(tap["t10_flat_annulus"][0]["loc"])
    c = math.sqrt(1e4 / 0.5)
    o = (c - 0.002) * 0.5
    band, in_hole = _band(hole, c, o)
    s32 = hills[:, :2].astype(f32)
    t32 = band.astype(f32)
    n = len(s32)
    best = np.full(n, np.inf, dtype=f32)
    arg = np.zeros(n, dtype=np.int64)
    for k in range(0, n, 2000):
        s = s32[k:k + 2000]
        dx = s[:, None, 0] - t32[None, :, 0]
        dy = s[:, None, 1] - t32[None, :, 1]
        dd = np.sqrt(dx * dx + dy * dy)
        best[k:k + 2000] = dd.min(1)
        arg[k:k + 2000] = dd.argmin(1)
    ins = np.array([in_hole(x, y) for x, y, _ in hills])
    for k in np.where(~ins)[0]:                     # in the annulus: the nearest grid node is its own target
        x, y = hills[k, 0], hills[k, 1]
        i0, j0 = math.floor((x - o) / c), math.floor((y - o) / c)
        for i in range(i0 - 1, i0 + 3):
            for j in range(j0 - 1, j0 + 3):
                tx, ty = i * c + o, j * c + o
                if in_hole(tx, ty):
                    continue
                dx, dy = f32(s32[k, 0]) - f32(tx), f32(s32[k, 1]) - f32(ty)
                best[k] = min(best[k], np.sqrt(f32(dx * dx) + f32(dy * dy)))
    z32 = hills[:, 2].astype(f32).astype(np.float64)
    pz = np.float64(f32(an["z"]))
    z = z32 + (pz - z32) * _mask(best, 50000.0).astype(np.float64)
    exact = z == flat[:, 2]
    ulps = {}
    for k in np.where(~exact)[0]:
        found = None
        for u in (1, -1, 2, -2, 3, -3):
            w = f32(best[k])
            for _ in range(abs(u)):
                w = np.nextafter(w, f32(np.inf if u > 0 else -np.inf))
            if z32[k] + (pz - z32[k]) * np.float64(_mask(np.array([w], dtype=f32), 50000.0)[0]) == flat[k, 2]:
                found = u
                break
        ulps[str(found)] = ulps.get(str(found), 0) + 1
    # the pure-Python nearest search (double distances, no float emulation): a lower bound on the port's cost
    pts = hills[:, :2].tolist()
    bucket = 2000.0
    grid = {}
    for x, y in band.tolist():
        grid.setdefault((math.floor(x / bucket), math.floor(y / bucket)), []).append((x, y))
    sample = random.Random(3).sample(range(n), 3000)
    t0 = time.perf_counter()
    for k in sample:
        x, y = pts[k]
        bx, by = math.floor(x / bucket), math.floor(y / bucket)
        b, r = math.inf, 0
        while r * bucket - bucket < min(b, 50000.0 + bucket):
            for i in range(bx - r, bx + r + 1):
                for j in ((by - r, by + r) if abs(i - bx) != r else range(by - r, by + r + 1)):
                    for tx, ty in grid.get((i, j), ()):
                        b = min(b, math.hypot(x - tx, y - ty))
            r += 1
    per = (time.perf_counter() - t0) / len(sample)
    return {"points": n, "in_circle": int(ins.sum()), "band_targets": len(band), "bit_exact": int(exact.sum()),
            "max_abs_cm": float(np.abs(z - flat[:, 2]).max()), "ulp_offsets_of_the_rest": ulps,
            "python_us_per_point": per * 1e6, "python_seconds_per_projection": per * n}


def blur(tap):
    pts = tap["t02_noise"][0]["loc"]
    r = 12000.0
    grid = {}
    for i, (x, y, _z) in enumerate(pts):
        grid.setdefault((math.floor(x / r), math.floor(y / r)), []).append(i)
    vals = [random.Random(2).random() for _ in pts]
    sample = random.Random(1).sample(range(len(pts)), 2000)
    t0 = time.perf_counter()
    nb = 0
    for i in sample:
        x, y, z = pts[i]
        cx, cy = math.floor(x / r), math.floor(y / r)
        s = 0.0
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j in grid.get((gx, gy), ()):
                    px, py, pz = pts[j]
                    if (px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2 <= r * r:
                        s += vals[j]
                        nb += 1
    per = (time.perf_counter() - t0) / len(sample)
    return {"us_per_point": per * 1e6, "neighbours_per_point": nb / len(sample),
            "seconds_two_iterations": 2 * per * len(pts), "note": "positions of the official hills output; "
            "the official blur runs on the DISTORTED positions (+-33000 cm), whose neighbourhoods are as large"}


def lerp(tap):
    a = tap["t10_flat_annulus"][0]["loc"]
    b = tap["t14_city_proj"][0]["loc"]
    out = tap["t16_lerp"][0]["loc"]
    r = tap["t15_ratio"][0]["values"]["None"]
    ok = sum(1 for p, q, s in zip(a, b, out) for k in range(3) if p[k] + (q[k] - p[k]) * r == s[k])
    return {"components": 3 * len(out), "bit_exact": ok, "ratio": r}


def main():
    with open(os.path.join(T24, "tap_a.json"), encoding="utf-8") as fh:
        tap = json.load(fh)
    res = {"source": "Saved/t24/tap_a.json (official taps, 2026-10-20)", "lerp": lerp(tap), "blur": blur(tap),
           "project": project(tap)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
