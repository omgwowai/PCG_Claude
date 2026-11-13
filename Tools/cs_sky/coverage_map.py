"""Offline map of the cloud coverage the material computes around a camera, to pick weather-map offsets.

Evaluates the same coverage expression as M_CS_CumulusCloud (weather map R, second-scale B modulation, CoverageBias /
CoverageScale) on a grid of world positions around the camera, then draws the camera, the sun azimuth and the stretch
of the sun line that lies inside the cloud layer.

Usage: C:\\Python314\\python.exe Tools/cs_sky/coverage_map.py --cam 0.585 0.019 0.247 --sun-az 146 --sun-el 31.1
           --wind 0 0 [--bias 0] [--extent 30] [--out Saved/Reports/cs_weather/coverage.png] [--search]
"""
import argparse
import math
import os

import numpy as np
from PIL import Image, ImageDraw

WEATHER = os.path.join("Saved", "CitySampleSky", "noise", "T_CS_CloudWeather.png")
SHAPE = os.path.join("Saved", "CitySampleSky", "noise", "T_CS_CloudShape_Atlas.png")
_SHAPE_SLICE = {}


def _shape_slice(z=0.37):
    """The two shape-volume slices around normalised depth z, as HxWx4 floats indexed [y, x] (atlas: 16 x 8 tiles)."""
    if z not in _SHAPE_SLICE:
        atlas = np.asarray(Image.open(SHAPE)).astype(np.float32) / 255.0
        n = 128
        zf = z * n - 0.5
        z0 = int(np.floor(zf)) % n
        z1 = (z0 + 1) % n
        f = zf - np.floor(zf)
        tiles = []
        for zi in (z0, z1):
            r, c = divmod(zi, 16)
            tiles.append(atlas[r * n:(r + 1) * n, c * n:(c + 1) * n])
        _SHAPE_SLICE[z] = tiles[0] * (1 - f) + tiles[1] * f
    return _SHAPE_SLICE[z]


def warp_offset(xkm, ykm, shape_km, warp_km):
    sl = _shape_slice()
    wn = sample(sl, xkm / (shape_km * 3.0), ykm / (shape_km * 3.0))
    return (wn[..., 1] - 0.5) * warp_km, (wn[..., 2] - 0.5) * warp_km


def sample(img, u, v):
    """Bilinear, wrapped sample of an HxWxC float image at uv arrays."""
    h, w = img.shape[:2]
    x = (u * w - 0.5) % w
    y = (v * h - 0.5) % h
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) +
            img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def coverage(img, xkm, ykm, wind, scale_km, bias, cscale, shape_km=5.0, warp_km=1.5):
    wx, wy = warp_offset(xkm, ykm, shape_km, warp_km)
    u = (xkm + wind[0] + wx) / scale_km
    v = (ykm + wind[1] + wy) / scale_km
    wm = sample(img, u, v)
    wm2 = sample(img, u * 0.37 + 0.21, v * 0.37 + 0.63)
    return np.clip(wm[..., 0] * (1.0 + (np.clip(wm2[..., 2] * 1.8, 0, 1) - 1.0) * 0.4) * cscale + bias, 0, 1)


def sun_line(cam, az, el, base_km, top_km, n=64):
    d = np.array([math.cos(math.radians(az)), math.sin(math.radians(az))])
    t0 = (base_km - cam[2]) / math.tan(math.radians(el))
    t1 = (top_km - cam[2]) / math.tan(math.radians(el))
    ts = np.linspace(t0, t1, n)
    return cam[0] + d[0] * ts, cam[1] + d[1] * ts, (t0, t1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", type=float, nargs=3, default=[0.585, 0.019, 0.247])
    ap.add_argument("--sun-az", type=float, default=146.0)
    ap.add_argument("--sun-el", type=float, default=31.1)
    ap.add_argument("--wind", type=float, nargs=2, default=[0.0, 0.0])
    ap.add_argument("--bias", type=float, default=0.0)
    ap.add_argument("--cscale", type=float, default=1.0)
    ap.add_argument("--scale", type=float, default=32.0)
    ap.add_argument("--base", type=float, default=1.34)
    ap.add_argument("--top", type=float, default=3.5)
    ap.add_argument("--extent", type=float, default=30.0)
    ap.add_argument("--out", default=os.path.join("Saved", "Reports", "cs_weather", "coverage.png"))
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--rich", type=float, default=0.4, help="target cloudy fraction of the view wedge")
    ap.add_argument("--block", type=float, default=0.0, help="coverage the sun line must reach somewhere")
    a = ap.parse_args()
    img = np.asarray(Image.open(WEATHER)).astype(np.float32) / 255.0
    cam = a.cam
    lx, ly, (t0, t1) = sun_line(cam, a.sun_az, a.sun_el, a.base, a.top)
    if a.search:
        best = []
        ang = np.radians(a.sun_az + np.linspace(-35, 35, 15))
        rr = np.linspace(2, 14, 13)
        wxk = cam[0] + np.outer(rr, np.cos(ang))
        wyk = cam[1] + np.outer(rr, np.sin(ang))
        th = np.linspace(0, 2 * np.pi, 16, endpoint=False)
        ox = cam[0] + np.concatenate([[0.0], 0.8 * np.cos(th), 1.5 * np.cos(th)])
        oy = cam[1] + np.concatenate([[0.0], 0.8 * np.sin(th), 1.5 * np.sin(th)])
        for wx in np.arange(0, 32, 0.5):
            for wy in np.arange(0, 32, 0.5):
                c = coverage(img, lx, ly, (wx, wy), a.scale, a.bias, a.cscale)
                cloudy = c > 0.35
                frac = float(cloudy.mean())
                edges = int(np.abs(np.diff(cloudy.astype(int))).sum())
                rich = float((coverage(img, wxk, wyk, (wx, wy), a.scale, a.bias, a.cscale) > 0.35).mean())
                over = float(coverage(img, ox, oy, (wx, wy), a.scale, a.bias, a.cscale).mean())
                block = float(c.max())
                score = (-abs(frac - 0.5) * 2 + min(edges, 3) * 0.2 - abs(rich - a.rich) * 1.5 - over * 2
                         - max(0.0, a.block - block) * 4)
                best.append((score, wx, wy, frac, edges, rich, over, block))
        best.sort(reverse=True)
        for b in best[:12]:
            print("score %.3f wind (%.1f, %.1f) sun-line cloudy %.2f edges %d wedge %.2f overhead %.2f max %.2f" % b)
        return
    ext = a.extent
    n = 600
    xs = np.linspace(cam[0] - ext, cam[0] + ext, n)
    ys = np.linspace(cam[1] - ext, cam[1] + ext, n)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    c = coverage(img, X, Y, a.wind, a.scale, a.bias, a.cscale)
    # image: up = +X (north), right = +Y (east)
    rgb = np.stack([c * 255] * 3, axis=-1).astype(np.uint8)
    rgb = np.flipud(np.transpose(rgb, (1, 0, 2)))
    im = Image.fromarray(np.ascontiguousarray(rgb)).convert("RGB")
    dr = ImageDraw.Draw(im)

    def px(xk, yk):
        return ((yk - (cam[1] - ext)) / (2 * ext) * n, n - (xk - (cam[0] - ext)) / (2 * ext) * n)

    cx, cy = px(cam[0], cam[1])
    dr.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(255, 0, 0), width=2)
    p0, p1 = px(lx[0], ly[0]), px(lx[-1], ly[-1])
    dr.line([p0, p1], fill=(255, 200, 0), width=3)
    for fov in (-37.5, 37.5):
        ang = math.radians(a.sun_az + 6 + fov)
        dr.line([(cx, cy), px(cam[0] + 20 * math.cos(ang), cam[1] + 20 * math.sin(ang))], fill=(0, 160, 255), width=1)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    im.save(a.out)
    cl = coverage(img, lx, ly, a.wind, a.scale, a.bias, a.cscale)
    print("sun line %.1f..%.1f km, coverage along it:" % (t0, t1), np.round(cl[::8], 2))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
