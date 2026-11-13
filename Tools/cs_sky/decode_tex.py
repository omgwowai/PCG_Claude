"""Decode the raw texel dumps written by rdc_export.py and render PNG previews.

Usage: C:\\Python314\\python.exe Tools/cs_sky/decode_tex.py --dir Saved/Reports/cs_weather/rdc [--only TAG ...]

For every <tag>.json + <tag>_s<slice>.bin in <dir>/tex it writes <dir>/png/<tag>[_s<slice>]_<view>.png where view is
  hdr     exposure-normalised RGB (99.5th percentile -> 0.85), filmic curve, sRGB
  lin     RGB clamped to [0,1], sRGB (for LUTs that already are 0..1, e.g. transmittance)
  cN      channel N alone, normalised to its 0.5..99.5 percentiles
  a       alpha channel, 0..1
and for 3D textures the same views of a few depth slices (zNNN) plus the last slice.
It also writes <dir>/png/index.json with the stats (min / max / mean per channel) of every decoded texture.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image


def _f11(bits, mbits):
    e = (bits >> mbits) & 0x1F
    m = bits & ((1 << mbits) - 1)
    m = m.astype(np.float32) / float(1 << mbits)
    out = np.where(e == 0, m * 2.0 ** -14, (1.0 + m) * np.power(2.0, e.astype(np.float32) - 15.0))
    return np.where(e == 31, np.float32(65504.0), out).astype(np.float32)


def decode(meta, raw):
    fmt = meta["fmt"]
    w, h, d = meta["w"], meta["h"], max(1, meta["d"])
    n = w * h * d
    if fmt in ("R16G16B16A16_FLOAT",):
        a = np.frombuffer(raw, np.float16, n * 4).astype(np.float32).reshape(d, h, w, 4)
    elif fmt in ("R32G32B32A32_FLOAT",):
        a = np.frombuffer(raw, np.float32, n * 4).reshape(d, h, w, 4)
    elif fmt in ("R32G32B32_FLOAT",):
        a = np.frombuffer(raw, np.float32, n * 3).reshape(d, h, w, 3)
    elif fmt in ("R16G16_FLOAT",):
        a = np.frombuffer(raw, np.float16, n * 2).astype(np.float32).reshape(d, h, w, 2)
    elif fmt in ("R32G32_FLOAT",):
        a = np.frombuffer(raw, np.float32, n * 2).reshape(d, h, w, 2)
    elif fmt in ("R16_FLOAT",):
        a = np.frombuffer(raw, np.float16, n).astype(np.float32).reshape(d, h, w, 1)
    elif fmt in ("R32_FLOAT", "D32_FLOAT"):
        a = np.frombuffer(raw, np.float32, n).reshape(d, h, w, 1)
    elif fmt in ("R11G11B10_FLOAT",):
        u = np.frombuffer(raw, np.uint32, n).reshape(d, h, w)
        a = np.stack([_f11(u & 0x7FF, 6), _f11((u >> 11) & 0x7FF, 6), _f11((u >> 22) & 0x3FF, 5)], axis=-1)
    elif fmt in ("R8G8B8A8_UNORM", "R8G8B8A8_UNORM_SRGB", "R8G8B8A8_TYPELESS"):
        a = np.frombuffer(raw, np.uint8, n * 4).astype(np.float32).reshape(d, h, w, 4) / 255.0
    elif fmt in ("B8G8R8A8_UNORM", "B8G8R8A8_UNORM_SRGB", "B8G8R8A8_TYPELESS"):
        a = np.frombuffer(raw, np.uint8, n * 4).astype(np.float32).reshape(d, h, w, 4)[..., [2, 1, 0, 3]] / 255.0
    elif fmt in ("R10G10B10A2_UNORM",):
        u = np.frombuffer(raw, np.uint32, n).reshape(d, h, w)
        a = np.stack([(u & 1023) / 1023.0, ((u >> 10) & 1023) / 1023.0, ((u >> 20) & 1023) / 1023.0,
                      ((u >> 30) & 3) / 3.0], axis=-1).astype(np.float32)
    elif fmt in ("R8_UNORM",):
        a = np.frombuffer(raw, np.uint8, n).astype(np.float32).reshape(d, h, w, 1) / 255.0
    elif fmt in ("R8G8_UNORM",):
        a = np.frombuffer(raw, np.uint8, n * 2).astype(np.float32).reshape(d, h, w, 2) / 255.0
    elif fmt in ("R16G16B16A16_UNORM",):
        a = np.frombuffer(raw, np.uint16, n * 4).astype(np.float32).reshape(d, h, w, 4) / 65535.0
    elif fmt in ("R32_UINT",):
        a = np.frombuffer(raw, np.uint32, n).astype(np.float32).reshape(d, h, w, 1)
    else:
        raise ValueError("unsupported format %s" % fmt)
    return a


def srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def filmic(x):
    # ACES fit (Narkowicz)
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0)


def to_png(img01, path):
    Image.fromarray((np.clip(img01, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)


def views(a2d, base, out_dir, kinds, stats_key, index, exposure=None):
    """a2d: HxWxC float array."""
    c = a2d.shape[-1]
    files = {}
    finite = np.where(np.isfinite(a2d), a2d, 0.0)
    if "hdr" in kinds and c >= 3:
        rgb = finite[..., :3]
        lum = rgb.mean(axis=-1)
        ref = exposure if exposure else float(np.percentile(lum, 99.5)) or 1.0
        img = srgb(filmic(rgb / max(ref, 1e-12) * 0.85 * 1.6))
        p = os.path.join(out_dir, base + "_hdr.png")
        to_png(img, p)
        files["hdr"] = os.path.basename(p)
    if "lin" in kinds and c >= 3:
        p = os.path.join(out_dir, base + "_lin.png")
        to_png(srgb(finite[..., :3]), p)
        files["lin"] = os.path.basename(p)
    if "ch" in kinds:
        for i in range(min(c, 4)):
            ch = finite[..., i]
            lo, hi = np.percentile(ch, [0.5, 99.5])
            if hi - lo < 1e-12:
                hi = lo + 1.0
            p = os.path.join(out_dir, base + "_c%d.png" % i)
            to_png(np.repeat(((ch - lo) / (hi - lo))[..., None], 3, -1), p)
            files["c%d" % i] = os.path.basename(p)
    if "a" in kinds and c == 4:
        p = os.path.join(out_dir, base + "_a.png")
        to_png(np.repeat(finite[..., 3:4], 3, -1), p)
        files["a"] = os.path.basename(p)
    st = {"min": [float(finite[..., i].min()) for i in range(c)],
          "max": [float(finite[..., i].max()) for i in range(c)],
          "mean": [float(finite[..., i].mean()) for i in range(c)]}
    index[stats_key] = {"files": files, "stats": st, "shape": list(a2d.shape)}
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join("Saved", "Reports", "cs_weather", "rdc"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--crop", nargs="*", default=[],
                    help="pool:view pairs, e.g. 1336x1328:843x1321 crops textures of the pool size to the view rect")
    ap.add_argument("--skip", nargs="*", default=[], help="tags to skip")
    a = ap.parse_args()
    tex_dir = os.path.join(a.dir, "tex")
    out_dir = os.path.join(a.dir, "png")
    os.makedirs(out_dir, exist_ok=True)
    index_path = os.path.join(out_dir, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    for fn in sorted(os.listdir(tex_dir)):
        if not fn.endswith(".json"):
            continue
        tag = fn[:-5]
        if a.only and not any(tag.startswith(o) for o in a.only):
            continue
        if any(tag == k for k in a.skip):
            continue
        meta = json.load(open(os.path.join(tex_dir, fn)))
        for f in meta["files"]:
            raw = open(os.path.join(tex_dir, f["file"]), "rb").read()
            try:
                arr = decode(meta, raw)
            except Exception as e:
                print("skip", tag, e)
                continue
            base = tag + ("_s%d" % f["slice"] if meta["arr"] > 1 else "")
            for pair in a.crop:
                pool, view = pair.split(":")
                pw, ph = [int(v) for v in pool.split("x")]
                vw, vh = [int(v) for v in view.split("x")]
                if arr.shape[2] == pw and arr.shape[1] == ph:
                    arr = arr[:, :vh, :vw]
            kinds = ("hdr", "lin", "ch", "a")
            if arr.shape[0] == 1:
                views(arr[0], base, out_dir, kinds, base, index)
            else:
                dn = arr.shape[0]
                for z in sorted(set([0, dn // 8, dn // 4, dn // 2, (3 * dn) // 4, dn - 1])):
                    views(arr[z], base + "_z%03d" % z, out_dir, kinds, base + "_z%03d" % z, index)
                # depth-wise view of the volume: average over z (shows the whole volume at once)
                views(arr.mean(axis=0), base + "_zmean", out_dir, kinds, base + "_zmean", index)
            print("decoded", base, meta["fmt"], arr.shape)
    json.dump(index, open(index_path, "w"), indent=1)


if __name__ == "__main__":
    main()
