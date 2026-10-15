"""Sampling with Python's own random numbers (spec E2: new layouts, not PCG's RNG)."""
from .plane import bbox, inside, signed_area


def area_m2(polygon):
    return (abs(signed_area(polygon.outer)) - sum(abs(signed_area(h)) for h in polygon.holes)) / 1e4


def contains(polygon, pt):
    return inside(pt, polygon.outer) and not any(inside(pt, h) for h in polygon.holes)


def scatter(polygon, per_m2, rng, max_tries_factor=50):
    """round(area * per_m2) uniform points in the polygon (holes excluded), by rejection."""
    n = int(round(area_m2(polygon) * per_m2))
    (x0, y0), (x1, y1) = bbox(polygon.outer)
    out, tries = [], 0
    while len(out) < n and tries < n * max_tries_factor + 100:
        tries += 1
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if contains(polygon, p):
            out.append(p)
    return out


def choose(n, ratio, rng):
    """Sorted indices of round(n * ratio) of n items (Filter_RandomChoice / RandomChoice)."""
    k = max(0, min(n, int(round(n * ratio))))
    return sorted(rng.sample(range(n), k))
