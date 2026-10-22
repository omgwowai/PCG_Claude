"""Sampling with Python's own random numbers (spec E2: new layouts, not PCG's RNG)."""
import math

from .plane import bbox, inside, signed_area


def area_m2(polygon):
    return (abs(signed_area(polygon.outer)) - sum(abs(signed_area(h)) for h in polygon.holes)) / 1e4


def contains(polygon, pt):
    return inside(pt, polygon.outer) and not any(inside(pt, h) for h in polygon.holes)


def scatter(polygon, per_m2, rng, max_tries_factor=50, notes=None):
    """round(area * per_m2) uniform points in the polygon (holes excluded), by rejection.

    When the tries run out first (a thin polygon in a large box) fewer points come back. Pass a stage's
    `ctx.notes` as `notes` and that shortfall is written there (review M4) instead of passing in silence;
    the points and the draws are the same either way."""
    n = int(round(area_m2(polygon) * per_m2))
    (x0, y0), (x1, y1) = bbox(polygon.outer)
    out, tries = [], 0
    while len(out) < n and tries < n * max_tries_factor + 100:
        tries += 1
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if contains(polygon, p):
            out.append(p)
    if notes is not None and len(out) < n:
        notes.append("scatter under-filled: %d of %d points after %d tries" % (len(out), n, tries))
    return out


def choose(n, ratio, rng, ceil=False):
    """Sorted indices of `round(n * ratio)` of n items by default -- this package's own count, which the
    `Filter_RandomChoice` callers use; it is NOT the engine's `PCGRandomChoice` count.

    `ceil=True` is the engine's `PCGRandomChoice` count, `CeilToInt(n * Clamp(Ratio, 0, 1))`
    (PCGRandomChoice.cpp:190, `NumOfElementsToKeep`): measured 2026-10-19 on stage 17, 57 hull vertices at
    `Ratio` 0.5152 kept 30, where round would keep 29. The chosen entries keep their input order
    (the node sorts the shuffled indices before copying)."""
    if ceil:
        k = max(0, min(n, int(math.ceil(n * min(max(float(ratio), 0.0), 1.0)))))
    else:
        k = max(0, min(n, int(round(n * ratio))))
    return sorted(rng.sample(range(n), k))


def keep_each(n, ratio, rng):
    """`Filter_RandomChoice` with `RandomPerDataset = true` (its default): one draw per data item,
    kept (`Selected`) when the draw is not above `Ratio`. This is a per-item Bernoulli cull, NOT a
    fixed count: the CoreProcess's `Filter_RandomChoice_CoreProcessLoop` stamps `@data.random` with
    `AttributeNoise` per item, `FilterDataByAttribute_0` (operator `Greater`, the node default) sends
    `random > Ratio` to `InsideFilter`, and `AddTags_1` tags that side `Unselected`. So a `Ratio` of
    0.9 keeps each item with probability 0.9 and the kept count varies from run to run.
    Returns one bool per item, True = selected."""
    r = float(ratio)
    return [not (rng.random() > r) for _ in range(n)]
