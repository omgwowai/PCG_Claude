# stills_check.py -- the cloud director's stills (wx_<preset>_<cam>_mid<age>.png, cs_cloud_director.py record "stills")
# against same-session static renders of the same camera (wx_<preset>_<cam>_<ref>.png, cs_weather.py batch). Metric: the
# 99.9th percentile of the absolute luma difference of 64 x 64 pixel block means. Two renders of one static look differed
# by up to 7.4 at this scale in Task 4 (temporal jitter phase, Lumen / fog history); a parameter missing from the
# director's material instance, or clouds that moved, shift cloud blocks by tens of levels.
#   C:\Python314\python.exe -P -E Tools/cs_weather/stills_check.py --ref s11 [--limit 10]
#   -> age 0 must stay within the limit (the director reproduces the static look), age 1200 must exceed it (the clouds
#      moved); Saved/Reports/cs_cloud_motion/stills_check.json; exit 1 when a verdict fails
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion", "stills_check.json")
W = np.array([0.2126, 0.7152, 0.0722])
BLOCK = 64


def _blocks(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) @ W
    h, w = a.shape[0] // BLOCK * BLOCK, a.shape[1] // BLOCK * BLOCK
    return a[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean(axis=(1, 3))


def block_p999(a_path, b_path):
    """99.9th percentile of |block mean of a - block mean of b| (64 px blocks, luma)."""
    return float(np.percentile(np.abs(_blocks(a_path) - _blocks(b_path)), 99.9))


def verdict(age0, age1200, limit):
    """(age 0 reproduces the static look, age 1200 moved)."""
    return age0 <= limit, age1200 > limit


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import cs_cloud_motion as M
    import cs_weather_presets as P
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--limit", type=float, default=10.0)
    a = ap.parse_args()
    rows, bad = [], 0
    for s in M.stills_list(P):
        cam = M.short_cam(s["cams"][0])
        ref = os.path.join(SHOTS, "wx_%s_%s_%s.png" % (s["preset"], cam, a.ref))
        d0 = block_p999(ref, os.path.join(SHOTS, s["names"][0] + ".png"))
        d1 = block_p999(ref, os.path.join(SHOTS, s["names"][1] + ".png"))
        ok0, ok1 = verdict(d0, d1, a.limit)
        bad += (not ok0) + (not ok1)
        rows.append({"preset": s["preset"], "age0": round(d0, 2), "age1200": round(d1, 2), "same": ok0, "moved": ok1})
        print("%-16s age0 %6.2f %s   age1200 %6.2f %s" % (s["preset"], d0, "ok" if ok0 else "DRIFT", d1,
                                                           "moved" if ok1 else "STILL"))
    json.dump({"ref": a.ref, "limit": a.limit, "rows": rows}, open(OUT, "w", encoding="utf-8"), indent=1)
    print("%d presets, %d failed verdicts" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
