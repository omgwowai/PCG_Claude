"""`Write_DistanceFrom` on points, as plain values (stage 18 first). No unreal import.

The primitive (`Write_DistanceFrom` -> `Write_DistanceFrom_CoreProcess`, exported 2026-10-20) runs, for a
point source and point targets:

  FilterDataByType_3, MergePoints_0   every target point set merged into ONE target set
  Branch_4 / Branch_5 (ComputeIn2D)   `$Position.Z` set to 0 on the sources and on the merged targets
                                      (`CopyAttributes_11/12` keep it in `__posZ`, restored afterwards)
  Distance_1 (Center / Center)        each source's distance to the nearest target, `MaximumDistance` cap
  AttributeMathsOp_6 (Normalized)     / MaximumDistance
  AttributeRemap_0 (UseRemap)         from [min, max] of the values over EVERY source item to
                                      [RemapOutputMin, RemapOutputMax] (`bAllowInverseRange`, no clamp)

`PCGDistance.cpp:342-407`: a source's centre is `Transform.TransformPosition(local box centre)`; a target's
centre is the ORIGIN of its octree bounds -- the point's box transformed (`FBox::TransformBy`) and taken back
as `(Min + Max) * 0.5`, which is `((c - e) + (c + e)) * 0.5` and can differ from the point's own location in
the last bit. Measured 2026-10-20 on stage 18's shore distance (308 785 sources, 37 832 targets): with the
targets' own locations 2 of 308 785 values differ by 1.4e-15; with the box-centre origin all are equal. The
nearest target is the one with the smallest squared distance strictly below `MaximumDistance^2` (the initial
`MinDistanceSquared`), so no target within reach gives exactly `MaximumDistance`. No target at all (an empty
target pin with `bOutputToAttribute`) gives `MaximumDistance` for every source too (read from the source, not
measured: every stage-18 run here has targets).

`AttributeRemap` (`PCGAttributeRemap.cpp:186-226`): `slope = (OutMax - OutMin) / (InMax - InMin)`, value
`slope * (v - InMin) + OutMin`; a point range (`InMax == InMin`) gives `(OutMin + OutMax) / 2`."""
import math


def remap(values, lo, hi, out_lo, out_hi):
    """`AttributeRemap` (Ranges, `bAllowInverseRange` true, no clamp) of `values` from [lo, hi]."""
    if hi - lo == 0:
        mid = (out_lo + out_hi) / 2.0
        return [mid for _ in values]
    slope = (out_hi - out_lo) / (hi - lo)
    return [slope * (v - lo) + out_lo for v in values]


def target_centre(loc, scale, bmin, bmax, quat=None):
    """The (x, y) origin of a target point's octree bounds: the box centre placed in the world, then
    `((c - e) + (c + e)) * 0.5` with `e` the transformed box's half-size (`FBox::TransformBy` then
    `GetCenter`). `quat` (x, y, z, w) is the point's rotation (identity when None)."""
    from .plane import quat_rotate
    q = tuple(quat) if quat is not None else (0.0, 0.0, 0.0, 1.0)
    o = [(bmin[a] + bmax[a]) * 0.5 * scale[a] for a in range(3)]
    e = [(bmax[a] - bmin[a]) * 0.5 * scale[a] for a in range(3)]
    if q == (0.0, 0.0, 0.0, 1.0):
        c = (loc[0] + o[0], loc[1] + o[1])
        ex = (abs(e[0]), abs(e[1]))
    else:
        d = quat_rotate(q, tuple(o))
        c = (loc[0] + d[0], loc[1] + d[1])
        axes = [quat_rotate(q, tuple(e[k] if a == k else 0.0 for a in range(3))) for k in range(3)]
        ex = (sum(abs(v[0]) for v in axes), sum(abs(v[1]) for v in axes))
    return (((c[0] - ex[0]) + (c[0] + ex[0])) * 0.5, ((c[1] - ex[1]) + (c[1] + ex[1])) * 0.5)


class Nearest2D:
    """The nearest target (x, y) within `max_distance` of a query, on a uniform grid of `cell` cm: the
    query's own cell and its eight neighbours hold every target within `cell`, so `cell >= max_distance`
    is exact; a query's result is `min(max_distance, nearest)`, the nearest taken strictly below
    `max_distance^2` as `PCGDistance` does."""

    def __init__(self, targets, max_distance, cell=None):
        self.max = float(max_distance)
        self.cell = float(cell or max_distance)
        if self.cell < self.max:
            raise ValueError("a %g cm grid cannot answer a %g cm reach" % (self.cell, self.max))
        self.grid = {}
        c = self.cell
        for p in targets:
            self.grid.setdefault((math.floor(p[0] / c), math.floor(p[1] / c)), []).append((p[0], p[1]))

    def distance(self, x, y):
        c = self.cell
        gx, gy = math.floor(x / c), math.floor(y / c)
        best = self.max * self.max
        grid = self.grid
        for i in (gx - 1, gx, gx + 1):
            for j in (gy - 1, gy, gy + 1):
                for qx, qy in grid.get((i, j), ()):
                    dx, dy = qx - x, qy - y
                    d = dx * dx + dy * dy
                    if d < best:
                        best = d
        return math.sqrt(best)


def distance_from(sources, targets, max_distance, out_lo, out_hi):
    """`Write_DistanceFrom` with `ComputeIn2D`, `Normalized` and `UseRemap` on: `sources` is a list of
    point sets, each a list of (x, y) centres; `targets` the merged targets' centres (`target_centre`).
    Returns one list of remapped values per source set (doubles, the `OutputAttribute` column)."""
    near = Nearest2D(targets, max_distance)
    m = float(max_distance)
    raw = [[near.distance(p[0], p[1]) / m for p in s] for s in sources]
    flat = [v for r in raw for v in r]
    if not flat:
        return [[] for _ in sources]
    lo, hi = min(flat), max(flat)
    return [remap(r, lo, hi, float(out_lo), float(out_hi)) for r in raw]
