"""The mesh terrain's vertex lattice as a height field. The engine extracts the terrain as one point per vertex on a
585.9375 cm lattice (docs/pypcg/stages/s01.md 0); the sections' seams repeat a vertex, which maps to one cell here."""
import math


class Lattice:
    """n x n vertices, k = j * n + i at world (x0 + i * s, y0 + j * s); z[k] is None where there is no vertex."""

    def __init__(self, n, s, x0, y0, z=None):
        self.n, self.s, self.x0, self.y0 = int(n), float(s), float(x0), float(y0)
        self.z = list(z) if z is not None else [None] * (self.n * self.n)

    @classmethod
    def from_locs(cls, locs, s):
        """(lattice, ks): ks[i] is the cell of locs[i]."""
        if not locs:
            return cls(0, s, 0.0, 0.0), []
        x0, y0 = min(p[0] for p in locs), min(p[1] for p in locs)
        x1, y1 = max(p[0] for p in locs), max(p[1] for p in locs)
        n = int(round(max(x1 - x0, y1 - y0) / s)) + 1
        lat = cls(n, s, x0, y0)
        ks = []
        for p in locs:
            k = int(round((p[1] - y0) / s)) * n + int(round((p[0] - x0) / s))
            lat.z[k] = float(p[2])
            ks.append(k)
        return lat, ks

    def copy(self):
        return Lattice(self.n, self.s, self.x0, self.y0, self.z)

    def k(self, i, j):
        return j * self.n + i

    def inside(self, i, j):
        return 0 <= i < self.n and 0 <= j < self.n

    def ij(self, x, y):
        return int(round((x - self.x0) / self.s)), int(round((y - self.y0) / self.s))

    def xy(self, k):
        j, i = divmod(k, self.n)
        return self.x0 + i * self.s, self.y0 + j * self.s

    def nearest(self, x, y):
        i, j = self.ij(x, y)
        if not self.inside(i, j):
            return None
        k = j * self.n + i
        return k if self.z[k] is not None else None

    def nearest_valid(self, x, y, reach=4):
        """The closest cell with a vertex within `reach` cells of (x, y), or None (a point off the lattice)."""
        i0, j0 = self.ij(x, y)
        best = None
        for j in range(j0 - reach, j0 + reach + 1):
            for i in range(i0 - reach, i0 + reach + 1):
                if self.inside(i, j) and self.z[j * self.n + i] is not None:
                    d = (i - i0) ** 2 + (j - j0) ** 2
                    if best is None or d < best[0]:
                        best = (d, j * self.n + i)
        return best[1] if best else None

    def height(self, x, y):
        """Bilinear height, the nearest vertex's where a corner is missing, None off the lattice."""
        fx, fy = (x - self.x0) / self.s, (y - self.y0) / self.s
        i, j = math.floor(fx), math.floor(fy)
        n = self.n
        if 0 <= i < n - 1 and 0 <= j < n - 1:
            z = self.z
            a, b, c, d = z[j * n + i], z[j * n + i + 1], z[(j + 1) * n + i], z[(j + 1) * n + i + 1]
            if a is not None and b is not None and c is not None and d is not None:
                u, v = fx - i, fy - j
                return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
        k = self.nearest(x, y)
        return self.z[k] if k is not None else None

    def _at(self, i, j):
        return self.z[j * self.n + i] if self.inside(i, j) else None

    def slope_deg(self, k):
        j, i = divmod(k, self.n)
        z0 = self.z[k]
        if z0 is None:
            return 0.0

        def d(a, b, s):
            if a is not None and b is not None:
                return (b - a) / (2.0 * s)
            if b is not None:
                return (b - z0) / s
            if a is not None:
                return (z0 - a) / s
            return 0.0
        gx = d(self._at(i - 1, j), self._at(i + 1, j), self.s)
        gy = d(self._at(i, j - 1), self._at(i, j + 1), self.s)
        return math.degrees(math.atan(math.hypot(gx, gy)))

    def cells_in_box(self, x0, y0, x1, y1):
        n, s = self.n, self.s
        i0, i1 = max(0, math.ceil((x0 - self.x0) / s)), min(n - 1, math.floor((x1 - self.x0) / s))
        j0, j1 = max(0, math.ceil((y0 - self.y0) / s)), min(n - 1, math.floor((y1 - self.y0) / s))
        z = self.z
        for j in range(j0, j1 + 1):
            row = j * n
            for i in range(i0, i1 + 1):
                if z[row + i] is not None:
                    yield row + i

    def coarse(self, step, half):
        """Every step-th vertex with |x|, |y| <= half, aligned on the vertex at the origin, as a lattice of its own
        (the A* grids of the river and the roads)."""
        ci, cj = self.ij(0.0, 0.0)
        m = int(half // (self.s * step))
        n = 2 * m + 1
        out = Lattice(n, self.s * step, self.x0 + (ci - m * step) * self.s, self.y0 + (cj - m * step) * self.s)
        for b in range(n):
            for a in range(n):
                i, j = ci + (a - m) * step, cj + (b - m) * step
                if self.inside(i, j):
                    out.z[b * n + a] = self.z[j * self.n + i]
        return out
