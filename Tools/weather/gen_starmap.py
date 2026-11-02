"""The star map of the star sphere (spec §6.1): an RGB texture with a dark background, a faint Milky Way band, faint
white stars, and bright stars tinted between blue and orange, the brightest with a glow. System Python only (numpy and
Pillow, which the editor's Python lacks). The command line writes STARMAP_PATH, Saved/Weather/T_WeatherStars.png at
2048 x 1024, which weather.py assets imports (plan ruling P5)."""
import os

import numpy as np
from PIL import Image

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STARMAP_PATH = os.path.join(_REPO, "Saved", "Weather", "T_WeatherStars.png")
WIDTH, HEIGHT = 2048, 1024

_TINT = np.array([0.15, 0.0, -0.15])   # per unit of tint: red up and blue down towards orange, the reverse for blue


def make_starmap(width, height, seed=7):
    """The star map as uint8 (height, width, 3), the same for the same arguments; u and v run 0..1 across the pixel
    centres. The background is 0..8, plus the band 12 exp(-(d / 0.08)^2) at a distance d in v from the band's centre
    line v = 0.5 + 0.18 sin(2 pi u). round(w h 0.01) faint stars are 20 + 70 r; round(w h 0.003) bright stars are
    90 + 165 r^0.7, tinted by t in -1..1 (red x (1 + 0.15 t), blue x (1 - 0.15 t)), and those above 220 light the
    3 x 3 pixels around them at half their colour. A glow wraps from the right edge to the left one, as the band does,
    and stops at the top and bottom rows."""
    rng = np.random.default_rng(seed)
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    d = v[:, None] - (0.5 + 0.18 * np.sin(2 * np.pi * u))[None, :]
    grey = rng.uniform(0.0, 8.0, (height, width)) + 12.0 * np.exp(-(d / 0.08) ** 2)
    img = np.repeat(grey[:, :, None], 3, axis=2)

    n = round(width * height * 0.01)
    x, y = rng.integers(0, width, n), rng.integers(0, height, n)
    np.maximum.at(img, (y, x), (20 + 70 * rng.random(n))[:, None])

    n = round(width * height * 0.003)
    x, y = rng.integers(0, width, n), rng.integers(0, height, n)
    b = 90 + 165 * rng.random(n) ** 0.7
    rgb = b[:, None] * (1 + rng.uniform(-1.0, 1.0, n)[:, None] * _TINT)
    glow = b > 220
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            np.maximum.at(img, (np.clip(y[glow] + dy, 0, height - 1), (x[glow] + dx) % width), 0.5 * rgb[glow])
    np.maximum.at(img, (y, x), rgb)
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def write(path=STARMAP_PATH, width=WIDTH, height=HEIGHT):
    """Write the star map as an RGB PNG at `path`, creating its directory when missing, and return the path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(make_starmap(width, height)).save(path)
    return path


if __name__ == "__main__":
    print(write())
