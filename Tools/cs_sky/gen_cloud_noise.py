"""Generate tileable cloud noise for the City Sample clear-sky cloud material.

Writes three PNGs (8-bit) into the output directory:
  T_CS_CloudShape_Atlas.png   128^3 RGBA, 16 x 8 tiles of 128 x 128 (slice z at column z % 16, row z // 16)
      R = Perlin-Worley (Perlin FBM remapped onto an inverted-Worley FBM floor, GPU Pro 7 p.101)
      G, B, A = inverted-Worley FBM at three increasing frequencies (base cell count 8, 16, 32)
  T_CS_CloudDetail_Atlas.png  64^3 RGB(A=255), 8 x 8 tiles of 64 x 64
      R, G, B = inverted-Worley FBM at three increasing frequencies (base cell count 4, 8, 16)
  T_CS_CloudWeather.png       512^2 RGBA, tileable
      R = cumulus coverage (clusters of cells with clear gaps), G = cloud height/type (0 low, 1 towering),
      B = a second, independent coverage field used to break up repetition, A = 255

The channel recipe follows S. Hillaire's TileableVolumeNoise and A. Schneider's Nubis notes; every noise is periodic over
the unit cube / square so the textures tile with WRAP addressing.

Usage: C:\\Python314\\python.exe Tools/cs_sky/gen_cloud_noise.py [--out DIR] [--seed N] [--preview]
"""
import argparse
import os
import time

import numpy as np
from PIL import Image


def _grid(n, period):
    c = (np.arange(n, dtype=np.float32) + 0.5) / n * period
    return np.meshgrid(c, c, c, indexing="ij")


def worley3(n, cells, rng):
    """1 - normalised distance to the nearest feature point, periodic with `cells` cells per tile."""
    pts = rng.random((cells, cells, cells, 3), dtype=np.float32)
    X, Y, Z = _grid(n, cells)
    ix, iy, iz = np.floor(X).astype(np.int32), np.floor(Y).astype(np.int32), np.floor(Z).astype(np.int32)
    best = np.full(X.shape, np.inf, dtype=np.float32)
    for dx in (-1, 0, 1):
        cx = ix + dx
        for dy in (-1, 0, 1):
            cy = iy + dy
            for dz in (-1, 0, 1):
                cz = iz + dz
                fp = pts[cx % cells, cy % cells, cz % cells]
                d2 = (cx + fp[..., 0] - X) ** 2 + (cy + fp[..., 1] - Y) ** 2 + (cz + fp[..., 2] - Z) ** 2
                np.minimum(best, d2, out=best)
    d = np.sqrt(best)
    return np.clip(1.0 - d, 0.0, 1.0)


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def perlin3(n, period, rng):
    """Gradient noise in about [-1, 1], periodic with `period` lattice cells per tile."""
    g = rng.normal(size=(period, period, period, 3)).astype(np.float32)
    g /= np.linalg.norm(g, axis=-1, keepdims=True)
    X, Y, Z = _grid(n, period)
    ix, iy, iz = np.floor(X).astype(np.int32), np.floor(Y).astype(np.int32), np.floor(Z).astype(np.int32)
    fx, fy, fz = X - ix, Y - iy, Z - iz
    u, v, w = _fade(fx), _fade(fy), _fade(fz)

    def corner(ox, oy, oz):
        gg = g[(ix + ox) % period, (iy + oy) % period, (iz + oz) % period]
        return gg[..., 0] * (fx - ox) + gg[..., 1] * (fy - oy) + gg[..., 2] * (fz - oz)

    x00 = corner(0, 0, 0) * (1 - u) + corner(1, 0, 0) * u
    x10 = corner(0, 1, 0) * (1 - u) + corner(1, 1, 0) * u
    x01 = corner(0, 0, 1) * (1 - u) + corner(1, 0, 1) * u
    x11 = corner(0, 1, 1) * (1 - u) + corner(1, 1, 1) * u
    y0 = x00 * (1 - v) + x10 * v
    y1 = x01 * (1 - v) + x11 * v
    return (y0 * (1 - w) + y1 * w) * 1.6


def _norm01(a, lo_pct=0.5, hi_pct=99.5):
    lo, hi = np.percentile(a, [lo_pct, hi_pct])
    return np.clip((a - lo) / max(hi - lo, 1e-6), 0.0, 1.0)


def remap(v, lo, hi, nlo, nhi):
    return nlo + (v - lo) * (nhi - nlo) / np.maximum(hi - lo, 1e-6)


def shape_volume(rng, n=128):
    t = time.time()
    w = {c: worley3(n, c, rng) for c in (8, 16, 32, 56, 64)}
    print("  worley octaves %.1fs" % (time.time() - t))
    perlin = sum(perlin3(n, p, rng) * a for p, a in ((8, 1.0), (16, 0.5), (32, 0.25))) / 1.75
    perlin = _norm01(perlin, 1.0, 99.0)
    pw_floor = w[8] * 0.625 + w[32] * 0.25 + w[56] * 0.125
    r = np.clip(remap(perlin, 0.0, 1.0, pw_floor, 1.0), 0.0, 1.0)
    g = w[8] * 0.625 + w[16] * 0.25 + w[32] * 0.125
    b = w[16] * 0.625 + w[32] * 0.25 + w[64] * 0.125
    a = w[32] * 0.75 + w[64] * 0.25
    return np.stack([_norm01(r), _norm01(g), _norm01(b), _norm01(a)], axis=-1)


def detail_volume(rng, n=64):
    w = {c: worley3(n, c, rng) for c in (4, 8, 16, 32)}
    r = w[4] * 0.625 + w[8] * 0.25 + w[16] * 0.125
    g = w[8] * 0.625 + w[16] * 0.25 + w[32] * 0.125
    b = w[16] * 0.75 + w[32] * 0.25
    return np.stack([_norm01(r), _norm01(g), _norm01(b), np.ones_like(r)], axis=-1)


def worley2(n, cells, rng):
    pts = rng.random((cells, cells, 2), dtype=np.float32)
    c = (np.arange(n, dtype=np.float32) + 0.5) / n * cells
    X, Y = np.meshgrid(c, c, indexing="ij")
    ix, iy = np.floor(X).astype(np.int32), np.floor(Y).astype(np.int32)
    best = np.full(X.shape, np.inf, dtype=np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            fp = pts[cx % cells, cy % cells]
            np.minimum(best, (cx + fp[..., 0] - X) ** 2 + (cy + fp[..., 1] - Y) ** 2, out=best)
    return np.clip(1.0 - np.sqrt(best), 0.0, 1.0)


def perlin2(n, period, rng):
    ang = rng.random((period, period), dtype=np.float32) * np.float32(2 * np.pi)
    g = np.stack([np.cos(ang), np.sin(ang)], axis=-1)
    c = (np.arange(n, dtype=np.float32) + 0.5) / n * period
    X, Y = np.meshgrid(c, c, indexing="ij")
    ix, iy = np.floor(X).astype(np.int32), np.floor(Y).astype(np.int32)
    fx, fy = X - ix, Y - iy
    u, v = _fade(fx), _fade(fy)

    def corner(ox, oy):
        gg = g[(ix + ox) % period, (iy + oy) % period]
        return gg[..., 0] * (fx - ox) + gg[..., 1] * (fy - oy)

    return ((corner(0, 0) * (1 - u) + corner(1, 0) * u) * (1 - v) + (corner(0, 1) * (1 - u) + corner(1, 1) * u) * v) * 1.4


def fbm2(n, base, octaves, rng):
    acc, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        acc = acc + perlin2(n, base * 2 ** o, rng) * amp
        tot += amp
        amp *= 0.5
    return _norm01(acc / tot)


def wrap_blur(a, radius, passes=3):
    """Periodic box blur (three passes approximate a Gaussian); softens the Voronoi creases of the Worley cells."""
    for _ in range(passes):
        for axis in (0, 1):
            acc = np.zeros_like(a)
            for k in range(-radius, radius + 1):
                acc += np.roll(a, k, axis=axis)
            a = acc / (2 * radius + 1)
    return a


def cumulus_cells(n, cells, rng, presence=0.6, rmin=0.30, rmax=0.95):
    """Discrete cumulus 'cells': each Worley feature point is a cloud with its own radius (cell units), presence and
    height. Returns (coverage dome in [0,1], height/type of the dominant cloud in [0,1]); periodic over the tile."""
    pts = rng.random((cells, cells, 2), dtype=np.float32)
    alive = (rng.random((cells, cells)) < presence).astype(np.float32)
    size = (rmin + (rmax - rmin) * rng.random((cells, cells)) ** 1.6).astype(np.float32)
    height = rng.random((cells, cells), dtype=np.float32)
    c = (np.arange(n, dtype=np.float32) + 0.5) / n * cells
    X, Y = np.meshgrid(c, c, indexing="ij")
    ix, iy = np.floor(X).astype(np.int32), np.floor(Y).astype(np.int32)
    cov = np.zeros(X.shape, dtype=np.float32)
    typ = np.zeros(X.shape, dtype=np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx, cy = (ix + dx) % cells, (iy + dy) % cells
            fp = pts[cx, cy]
            d = np.sqrt((ix + dx + fp[..., 0] - X) ** 2 + (iy + dy + fp[..., 1] - Y) ** 2)
            bump = np.clip(1.0 - d / size[cx, cy], 0.0, 1.0) ** 0.6 * alive[cx, cy]
            # bigger clouds grow taller (cumulus congestus), with some randomness
            h = np.clip(0.25 + 0.75 * (size[cx, cy] - rmin) / (rmax - rmin) * (0.5 + height[cx, cy]), 0.0, 1.0)
            win = bump > cov
            typ = np.where(win, h, typ)
            cov = np.maximum(cov, bump)
    return cov, typ


def weather_map(rng, n=512):
    # fair-weather cumulus: discrete clouds of mixed sizes at two scales, thinned by a low-frequency field so there
    # are crowded patches and wide blue gaps; G carries each cloud's height (bigger clouds are taller)
    big, big_t = cumulus_cells(n, 14, rng, presence=0.55, rmin=0.35, rmax=0.95)
    small, small_t = cumulus_cells(n, 34, rng, presence=0.5, rmin=0.25, rmax=0.8)
    field = fbm2(n, 3, 4, rng)
    gate = np.clip((field - 0.25) / 0.45, 0.0, 1.0)
    cov = np.maximum(big * (0.55 + 0.45 * gate), small * 0.8 * gate)
    ctype = np.where(big * (0.55 + 0.45 * gate) >= small * 0.8 * gate, big_t, small_t * 0.6)
    cov = wrap_blur(cov, 1, 2)
    ctype = wrap_blur(ctype, 2, 2)
    cov2 = _norm01(wrap_blur(worley2(n, 15, rng), 3) * 0.5 + fbm2(n, 5, 4, rng) * 0.6)
    a = np.ones_like(cov)
    return np.stack([np.clip(cov, 0, 1), np.clip(ctype, 0, 1), cov2, a], axis=-1)


def atlas(vol, cols):
    n = vol.shape[0]
    rows = n // cols
    out = np.zeros((rows * n, cols * n, vol.shape[-1]), dtype=np.float32)
    for z in range(n):
        r, c = divmod(z, cols)
        # volume index order is [x, y, z]; an image row is y, a column is x
        out[r * n:(r + 1) * n, c * n:(c + 1) * n] = np.transpose(vol[:, :, z], (1, 0, 2))
    return out


def to_png(a, path):
    img = np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)
    mode = "RGBA" if img.shape[-1] == 4 else "RGB"
    Image.fromarray(img, mode).save(path)
    print("  wrote", path, img.shape)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("Saved", "CitySampleSky", "noise"))
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    t0 = time.time()
    print("shape 128^3 ...")
    shape = shape_volume(rng)
    to_png(atlas(shape, 16), os.path.join(args.out, "T_CS_CloudShape_Atlas.png"))
    print("detail 64^3 ...")
    detail = detail_volume(rng)
    to_png(atlas(detail, 8), os.path.join(args.out, "T_CS_CloudDetail_Atlas.png"))
    print("weather 512^2 ...")
    wm = weather_map(rng)
    to_png(np.transpose(wm, (1, 0, 2)), os.path.join(args.out, "T_CS_CloudWeather.png"))
    if args.preview:
        prev = []
        for vol in (shape, detail):
            sl = vol[:, :, vol.shape[2] // 3]
            chans = [np.repeat(sl[..., c:c + 1], 3, axis=-1) for c in range(min(4, sl.shape[-1]))]
            row = np.concatenate([np.kron(ch, np.ones((128 // vol.shape[0] * 2, 128 // vol.shape[0] * 2, 1)))
                                  for ch in chans], axis=1)
            prev.append(row)
        w = max(p.shape[1] for p in prev)
        prev = [np.pad(p, ((0, 0), (0, w - p.shape[1]), (0, 0))) for p in prev]
        to_png(np.concatenate(prev, axis=0), os.path.join(args.out, "preview_slices.png"))
        to_png(np.concatenate([np.repeat(wm[..., c:c + 1], 3, axis=-1) for c in range(3)], axis=1),
               os.path.join(args.out, "preview_weather.png"))
    print("done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
