"""Value noise for the world stages: deterministic in (x, y, seed), pure Python."""
import math


def _h(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 16777215.0


def value(x, y, seed=0):
    """Smooth value noise in [0, 1], one lattice cell per unit."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    u, v = fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy)
    a, b = _h(ix, iy, seed), _h(ix + 1, iy, seed)
    c, d = _h(ix, iy + 1, seed), _h(ix + 1, iy + 1, seed)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm(x, y, seed=0, octaves=5, lacunarity=2.0, gain=0.5):
    """Fractal sum of signed value noise, normalised to [-1, 1]."""
    total, amp, norm, f = 0.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        total += amp * (2.0 * value(x * f, y * f, seed + 1013 * o) - 1.0)
        norm += amp
        amp *= gain
        f *= lacunarity
    return total / norm


def ridged(x, y, seed=0, octaves=4, lacunarity=2.0, gain=0.5):
    """Ridged fractal in [0, 1]: sharp crests where the signed noise crosses zero."""
    total, amp, norm, f = 0.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        r = 1.0 - abs(2.0 * value(x * f, y * f, seed + 7919 * o) - 1.0)
        total += amp * r * r
        norm += amp
        amp *= gain
        f *= lacunarity
    return total / norm
