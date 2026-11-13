# motion_check.py -- jumps in a recorded clip (spec §6.2). Every frame is box-downscaled 8x in luma (the clouds' sampling
# noise averages out) and compared with the one before. A frame whose change exceeds FACTOR x the clip's median change
# (the median over every frame pair, floored at FLOOR levels) and LOCAL_FACTOR x the median of the RADIUS frames on
# each side is a jump.
#   C:\Python314\python.exe -P -E Tools/cs_weather/motion_check.py <clip> [--from 30] [--to 451] [--factor 3]
#   -> Saved/Reports/cs_cloud_motion/checks/<clip>.json and <clip>.png (the change per frame); exit 1 on a jump
import argparse
import glob
import json
import os
import statistics
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion")
FLOOR = 0.05
LOCAL_FACTOR = 1.75       # smallest real jump measured: 2.07 x its neighbours (water pop); motion peaks reach ~1.5 x
RADIUS = 8
W = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def luma8(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) @ W
    h, w = a.shape[0] // 8 * 8, a.shape[1] // 8 * 8
    return a[:h, :w].reshape(h // 8, 8, w // 8, 8).mean(axis=(1, 3))


def diffs(paths):
    """d[k] = mean |luma8(frame k) - luma8(frame k-1)|; d[0] = 0."""
    out, prev = [0.0], luma8(paths[0])
    for p in paths[1:]:
        cur = luma8(p)
        out.append(float(np.abs(cur - prev).mean()))
        prev = cur
    return out


def jumps(d, lo, hi, factor, local_factor=LOCAL_FACTOR, radius=RADIUS):
    """Frames k in [lo, hi) whose change exceeds factor x the median change of the whole clip (spec §6.2) and also
    local_factor x the median of the `radius` frames on each side (Task 11 ruling): a jump stands out from its own
    neighbourhood; fast motion in the bright part of a clip whose other part is dark rises and falls with it."""
    med = max(statistics.median(d[1:]), FLOOR) if len(d) > 1 else FLOOR
    out = []
    for k in range(max(lo, 1), min(hi, len(d))):
        if d[k] <= factor * med:
            continue
        near = d[max(1, k - radius):k] + d[k + 1:k + 1 + radius]
        if not near or d[k] > local_factor * max(statistics.median(near), FLOOR):
            out.append(k)
    return out


def plot(d, flagged, lo, hi, path):
    w, h = 900, 240
    im = Image.new("RGB", (w, h), (250, 250, 250))
    dr = ImageDraw.Draw(im)
    top = max(d) or 1.0

    def x(k):
        return 20 + (w - 40) * k / max(len(d) - 1, 1)

    def y(v):
        return h - 20 - (h - 40) * v / top

    dr.rectangle([x(lo), 10, x(max(hi - 1, lo)), h - 20], fill=(230, 238, 250))
    dr.line([(x(k), y(v)) for k, v in enumerate(d)], fill=(40, 90, 160), width=2)
    for k in flagged:
        dr.ellipse([x(k) - 4, y(d[k]) - 4, x(k) + 4, y(d[k]) + 4], outline=(200, 40, 40), width=2)
    im.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--from", dest="lo", type=int, default=1)
    ap.add_argument("--to", dest="hi", type=int, default=10 ** 9)
    ap.add_argument("--factor", type=float, default=3.0)
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(BASE, "frames", a.clip, "f_*.png")))
    if len(paths) < 3:
        print("%s: %d frames" % (a.clip, len(paths)))
        return 2
    d = diffs(paths)
    flagged = jumps(d, a.lo, a.hi, a.factor)
    out = os.path.join(BASE, "checks")
    os.makedirs(out, exist_ok=True)
    res = {"clip": a.clip, "frames": len(paths), "median": round(statistics.median(d[1:]), 4), "max": round(max(d), 4),
           "range": [max(a.lo, 1), min(a.hi, len(d))], "factor": a.factor, "jumps": flagged,
           "d": [round(v, 4) for v in d]}
    json.dump(res, open(os.path.join(out, a.clip + ".json"), "w", encoding="utf-8"), indent=1)
    plot(d, flagged, max(a.lo, 1), min(a.hi, len(d)), os.path.join(out, a.clip + ".png"))
    print({k: res[k] for k in ("clip", "frames", "median", "max", "jumps")})
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
