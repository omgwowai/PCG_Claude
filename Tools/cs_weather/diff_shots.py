# diff_shots.py -- how far apart two renders of the same camera are, to check that a material change left a look alone.
#   C:\Python314\python.exe -P -E Tools/cs_weather/diff_shots.py <a.png> <b.png> [--out diff.png]
# Prints the mean absolute sRGB difference per channel and the 99th / 99.9th percentile of the luma difference after an
# 8x box downscale (temporal noise of the volumetric clouds averages out there; a real change of shape does not).
# Two renders of the unchanged scene differ by about 1 (mean) and a few levels (p99.9); a changed cloud shape by tens.
import argparse
import sys

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def box(a, k):
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    return a[:h, :w].reshape(h // k, k, w // k, k, -1).mean(axis=(1, 3))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out")
    o = ap.parse_args()
    a, b = load(o.a), load(o.b)
    if a.shape != b.shape:
        print("size differs", a.shape, b.shape)
        return 2
    d = np.abs(a - b)
    w = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    dl = np.abs(box(a, 8) @ w - box(b, 8) @ w)
    res = {"mean_rgb": [round(float(x), 2) for x in d.reshape(-1, 3).mean(axis=0)],
           "p99_luma8": round(float(np.percentile(dl, 99)), 2), "p999_luma8": round(float(np.percentile(dl, 99.9)), 2),
           "max_luma8": round(float(dl.max()), 2)}
    print(res)
    if o.out:
        Image.fromarray(np.clip(d * 8.0, 0, 255).astype(np.uint8)).save(o.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
