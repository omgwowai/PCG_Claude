"""Field filters for the vegetation layers: a sliding-window minimum (the valley floor under a point) and D8 flow
accumulation (where water gathers: gullies and the river's banks)."""
import math
from collections import deque

_D8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _min_line(vals, r):
    n = len(vals)
    out = [0.0] * n
    dq = deque()
    for i in range(n + r):
        if i < n:
            while dq and vals[dq[-1]] >= vals[i]:
                dq.pop()
            dq.append(i)
        c = i - r
        if c >= 0:
            while dq[0] < c - r:
                dq.popleft()
            out[c] = vals[dq[0]]
    return out


def min_filter(lat, r):
    """The minimum z over the (2r+1)^2 window around every vertex (separable), None where there is no vertex."""
    n, inf = lat.n, float("inf")
    rows = [_min_line([inf if z is None else z for z in lat.z[j * n:(j + 1) * n]], r) for j in range(n)]
    out = [None] * (n * n)
    for i in range(n):
        col = _min_line([rows[j][i] for j in range(n)], r)
        for j in range(n):
            if lat.z[j * n + i] is not None:
                out[j * n + i] = col[j]
    return out


def flow_accumulation(lat):
    """D8: every vertex passes its count (itself plus everything upstream) to its steepest lower neighbour."""
    n, z = lat.n, lat.z
    acc = [0 if v is None else 1 for v in z]
    for k in sorted((k for k, v in enumerate(z) if v is not None), key=lambda k: -z[k]):
        j, i = divmod(k, n)
        best, drop = None, 0.0
        for di, dj in _D8:
            ii, jj = i + di, j + dj
            if 0 <= ii < n and 0 <= jj < n:
                v = z[jj * n + ii]
                if v is not None:
                    d = (z[k] - v) / math.hypot(di, dj)
                    if d > drop:
                        best, drop = jj * n + ii, d
        if best is not None:
            acc[best] += acc[k]
    return acc
