"""A* on a Lattice. The video's trick for roads that follow the terrain: search more directions than the eight
grid neighbours (MOVES16 adds the knight moves), so paths are not forced into 45-degree zigzags."""
import heapq
import math

MOVES8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
MOVES16 = MOVES8 + [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]


def search(lat, starts, goals, step_cost, moves=MOVES8, h_scale=1.0):
    """starts {k: initial cost}, goals {k}; step_cost(ka, kb, length_cm) -> cost or None (blocked). The heuristic is
    h_scale x the straight distance to the nearest goal (only with <= 8 goals; 0 turns it off): keep h_scale at or
    below the cheapest cost per cm for an optimal path. Returns the cells start .. goal, or None."""
    goals = set(goals)
    if not goals:
        return None
    n = lat.n
    gxy = [lat.xy(k) for k in goals] if h_scale > 0 and len(goals) <= 8 else None

    def h(k):
        if not gxy:
            return 0.0
        x, y = lat.xy(k)
        return h_scale * min(math.hypot(x - gx, y - gy) for gx, gy in gxy)

    inf = float("inf")
    g, came, heap, done = {}, {}, [], set()
    for k, g0 in starts.items():
        if k is not None and lat.z[k] is not None:
            g[k] = g0
            heapq.heappush(heap, (g0 + h(k), g0, k))
    steps = [(di, dj, lat.s * math.hypot(di, dj)) for di, dj in moves]
    while heap:
        _f, gk, k = heapq.heappop(heap)
        if k in done or gk > g.get(k, inf):
            continue
        if k in goals:
            path = [k]
            while path[-1] in came:
                path.append(came[path[-1]])
            return path[::-1]
        done.add(k)
        j, i = divmod(k, n)
        for di, dj, length in steps:
            ii, jj = i + di, j + dj
            if not (0 <= ii < n and 0 <= jj < n):
                continue
            kk = jj * n + ii
            if lat.z[kk] is None or kk in done:
                continue
            c = step_cost(k, kk, length)
            if c is None:
                continue
            ng = gk + c
            if ng < g.get(kk, inf):
                g[kk], came[kk] = ng, k
                heapq.heappush(heap, (ng + h(kk), ng, kk))
    return None
