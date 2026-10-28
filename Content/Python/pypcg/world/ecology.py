"""PyWorld vegetation communities (docs/superpowers/specs/2026-10-23-pyworld-vegetation-ecology-design.md).

Ecological fields on the terrain's vertex lattice (slope, height above the valley floor, flow, distances to the
river, the roads and the buildings, sun exposure, moisture, forest potential), the community at every sample, and the
layered scattering: canopy trees with spacing by crown, shrubs on forest edges, river banks, forest gaps and
hedgerows, ground plants in clumps (grass, flowers in patches of their own, ferns, leaf litter, moss), dead wood,
and rock clusters. No unreal import."""
import math

from . import SEA_Z, geom, hydro, noise
from .flora import HEIGHT, SPECIES

FLOOR_CELLS = 100
ROCK_SLOPE = 42.0              # bare rock from here; forests still climb the 34..42 degree slopes, thinner
COMMUNITIES = ("forest", "edge", "meadow", "riparian", "montane", "rock", "village")


def smooth(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def align(yaw, gx, gy, k):
    """(pitch, yaw, roll) turning a mesh's up axis k of the way onto the terrain normal (-gx, -gy, 1) (UE's
    FRotationMatrix: pitch tilts +X up, roll tilts +Y down)."""
    if k <= 0.0 or (gx == 0.0 and gy == 0.0):
        return 0.0, yaw, 0.0
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    sf, sr = (gx * c + gy * s) * k, (-gx * s + gy * c) * k
    pitch = math.atan(sf)
    return math.degrees(pitch), yaw, -math.degrees(math.atan(sr * math.cos(pitch)))


class Fields:
    """Per-vertex fields over the vertices within `extent` (+ margin) of the lattice centre; None elsewhere."""

    def __init__(self, lat, ex, footprints, seed, extent):
        self.lat, self.ex, self.seed = lat, ex, seed
        n = lat.n
        half = (n - 1) * lat.s / 2.0
        self.cx, self.cy = lat.x0 + half, lat.y0 + half
        e = extent + 2.0 * lat.s
        rel = hydro.min_filter(lat, FLOOR_CELLS)
        acc = hydro.flow_accumulation(lat)
        cent = _CentroidIndex(footprints)
        N = n * n
        self.slope, self.rel, self.acc = [None] * N, [None] * N, acc
        self.riv, self.line, self.ring = [1e9] * N, [1e9] * N, [False] * N
        self.bld, self.sun, self.moist, self.forest = [1e9] * N, [0.5] * N, [0.0] * N, [0.0] * N
        self.comm = [None] * N
        for k in range(N):
            z = lat.z[k]
            if z is None:
                continue
            x, y = lat.xy(k)
            if abs(x - self.cx) > e or abs(y - self.cy) > e:
                continue
            sl = lat.slope_deg(k)
            self.slope[k] = sl
            r = z - rel[k]
            self.rel[k] = r
            self.riv[k] = ex.river_gap(x, y)
            self.line[k] = ex.line_gap(x, y)
            self.ring[k] = ex.rings.near(x, y, 1100.0)
            self.bld[k] = cent.nearest(x, y, 15000.0)
            g = lat.surface(x, y)
            if g is not None and sl > 1.0 and (g[1] or g[2]):
                gx, gy = g[1], g[2]
                gl = math.hypot(gx, gy)
                north = -gx / gl                      # the slope faces +X ("north"): the shaded side
                self.sun[k] = 0.5 - 0.5 * north * min(1.0, sl / 20.0)
            self.moist[k] = self._moisture(k, r)
            self.forest[k] = self._forest(k, x, y, z, sl, r)
            self.comm[k] = self._community(k, z, sl, r)

    def _moisture(self, k, rel):
        riv = self.riv[k]
        m = max(math.exp(-max(0.0, riv) / 2500.0) if riv < 1e8 else 0.0,
                min(1.0, math.log1p(self.acc[k]) / math.log1p(800.0)) * 0.8,
                0.35 * (1.0 - smooth(0.0, 4000.0, rel)))
        return min(1.0, max(0.0, m + 0.3 * (0.5 - self.sun[k])))

    def _forest(self, k, x, y, z, sl, rel):
        if z < SEA_Z + 100.0:
            return 0.0
        if rel < 1500.0:
            base = 0.2
        elif rel < 5000.0:
            base = 0.2 + 0.65 * smooth(1500.0, 5000.0, rel)
        elif rel < 17000.0:
            base = 0.85
        else:
            base = 0.85 - 0.5 * smooth(17000.0, 24000.0, rel)
        if sl >= 34.0:
            base *= 0.75
        base += 0.1 * self.moist[k]
        base *= smooth(3000.0, 12000.0, self.bld[k])           # pasture around the settlements
        s = self.seed
        base += 0.42 * noise.fbm(x / 26000.0, y / 26000.0, s + 101, 3) + 0.14 * noise.fbm(x / 6000.0, y / 6000.0, s + 103, 2)
        return smooth(0.36, 0.70, base)

    def _community(self, k, z, sl, rel):
        if z < SEA_Z + 100.0:
            return None
        if sl >= ROCK_SLOPE:
            return "rock"
        if (self.riv[k] < 2500.0 and sl < 22.0) or (self.acc[k] >= 300 and sl < 25.0):
            return "riparian"
        f = self.forest[k]
        if rel >= 19000.0 and f < 0.75:
            return "montane"
        if f >= 0.75:
            return "forest"
        if f >= 0.15:
            return "edge"
        if self.bld[k] < 3500.0:
            return "village"
        return "meadow"

    def at(self, x, y):
        k = self.lat.nearest(x, y)
        return k if k is not None and self.comm[k] is not None else None

    def edgeness(self, k):
        return max(0.0, 1.0 - abs(self.forest[k] - 0.45) / 0.45)


class _CentroidIndex:
    def __init__(self, rings, cell=5000.0):
        self.cell, self.b = cell, {}
        for r in rings:
            x, y = geom.centroid(r)
            self.b.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y))

    def nearest(self, x, y, maxd):
        c, best = self.cell, 1e9
        reach = int(math.ceil(maxd / c))
        ix, iy = math.floor(x / c), math.floor(y / c)
        for bx in range(ix - reach, ix + reach + 1):
            for by in range(iy - reach, iy + reach + 1):
                for px, py in self.b.get((bx, by), ()):
                    d = math.hypot(px - x, py - y)
                    if d < best:
                        best = d
        return best


class Spacing:
    """Discs (x, y, r) bucketed on a grid: a new disc keeps `factor` x (r + r') from every other."""

    def __init__(self, cell=1000.0, rmax=700.0):
        self.cell, self.rmax, self.b = cell, rmax, {}

    def free(self, x, y, r, factor=0.55):
        c = self.cell
        reach = int(math.ceil((r + self.rmax) * factor / c))
        ix, iy = math.floor(x / c), math.floor(y / c)
        for bx in range(ix - reach, ix + reach + 1):
            for by in range(iy - reach, iy + reach + 1):
                for px, py, pr in self.b.get((bx, by), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < ((r + pr) * factor) ** 2:
                        return False
        return True

    def nearest_within(self, x, y, d):
        c = self.cell
        reach = int(math.ceil(d / c))
        ix, iy = math.floor(x / c), math.floor(y / c)
        for bx in range(ix - reach, ix + reach + 1):
            for by in range(iy - reach, iy + reach + 1):
                for px, py, _pr in self.b.get((bx, by), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < d * d:
                        return True
        return False

    def add(self, x, y, r):
        self.b.setdefault((math.floor(x / self.cell), math.floor(y / self.cell)), []).append((x, y, r))


def weighted(rng, mix):
    t = rng.uniform(0.0, sum(w for _n, w in mix))
    for name, w in mix:
        t -= w
        if t <= 0.0:
            return name
    return mix[-1][0]


# ---- community mixes (species, weight)
TREE_MIX = {
    "forest": [("Beech", 5.0), ("Hornbeam", 4.0), ("Maple", 1.6), ("Aspen", 0.5)],
    "forest_moist": [("Hornbeam", 4.0), ("Beech", 2.0), ("Alder", 1.5), ("Maple", 1.5), ("Aspen", 0.7)],
    "young": [("BeechYoung", 3.0), ("HornbeamSmall", 3.0), ("MapleYoung", 2.0), ("Hazel", 1.5)],
    "edge": [("Aspen", 3.0), ("Hazel", 3.0), ("HornbeamSmall", 2.0), ("MapleYoung", 1.5), ("BeechYoung", 1.0),
             ("Hornbeam", 1.5), ("Maple", 1.0)],
    "riparian": [("Alder", 6.0), ("Hazel", 1.5), ("Aspen", 1.0), ("HornbeamSmall", 1.0)],
    "montane": [("Hornbeam", 1.0), ("HornbeamSmall", 2.0), ("Aspen", 2.0), ("DeadTree", 1.0), ("BeechYoung", 1.0)],
    "meadow": [("HornbeamField", 4.0), ("Maple", 1.0), ("Beech", 0.7), ("Aspen", 1.0)],
    "village": [("HornbeamField", 2.0), ("Hazel", 2.0), ("MapleYoung", 1.0), ("Maple", 1.0)],
    "rock": [("DeadTree", 1.0), ("HornbeamSmall", 1.0), ("Aspen", 1.0)],
    "hedge": [("HornbeamField", 2.0), ("Maple", 1.0), ("Hazel", 2.0)],
}
SHRUB_MIX = {
    "edge": [("Elderberry", 3.0), ("HazelSmall", 2.5), ("Sapling", 3.0), ("AspenSapling", 1.0), ("MapleSapling", 1.0)],
    "forest": [("Sapling", 4.0), ("Seedling", 3.0), ("Elderberry", 1.0), ("HazelSmall", 1.0), ("MapleSapling", 1.0)],
    "riparian": [("Elderberry", 4.0), ("HazelSmall", 3.0), ("Sapling", 2.0)],
    "meadow": [("Elderberry", 3.0), ("HazelSmall", 2.0), ("Sapling", 1.0)],
    "village": [("Elderberry", 3.0), ("HazelSmall", 2.0)],
    "montane": [("Sapling", 2.0), ("Seedling", 3.0), ("AspenSapling", 1.0)],
    "hedge": [("Elderberry", 4.0), ("HazelSmall", 3.0), ("Sapling", 3.0), ("MapleSapling", 1.0)],
}
# ground cover under each community when no flower patch wins: (species or None, weight)
GROUND_BASE = {
    "meadow": [("Kikuyu", 4.5), ("KikuyuSmall", 1.5), ("WildGrass", 3.0), (None, 0.6)],
    "village": [("Kikuyu", 5.0), ("KikuyuSmall", 2.0), ("Clover", 1.0), (None, 1.5)],
    "edge": [("WildGrass", 3.5), ("Kikuyu", 2.0), ("Fern", 1.5), ("Leaves", 1.0), ("BeechFern", 0.6), (None, 0.5)],
    "forest": [("Leaves", 4.0), ("Fern", 2.5), ("BeechFern", 1.8), ("LadyFern", 1.8), ("Moss", 0.8),
               ("GroundCover", 1.0), ("Ivy", 0.8), ("WildGrass", 0.5), (None, 0.3)],
    "riparian": [("WildGrass", 4.5), ("LadyFern", 1.5), ("Fern", 1.0), ("Kikuyu", 1.5), ("Clover", 0.6), (None, 0.3)],
    "montane": [("KikuyuSmall", 2.5), ("WildGrass", 1.5), ("Pebbles", 0.4), ("Moss", 0.3), (None, 3.0)],
    "rock": [("Pebbles", 0.6), ("KikuyuSmall", 1.0), ("Moss", 0.5), (None, 6.0)],
}
# flower / herb patches: species -> (noise scale cm, threshold, suitability per community)
PATCHES = {
    "Windflower": (5000.0, 0.62, {"forest": 0.7, "edge": 0.6, "riparian": 0.3, "meadow": 0.15}),
    "Archangel": (4000.0, 0.64, {"forest": 0.5, "edge": 0.6}),
    "Lily": (3500.0, 0.68, {"forest": 0.4, "edge": 0.4}),
    "Periwinkle": (3000.0, 0.68, {"edge": 0.5, "village": 0.4, "forest": 0.2}),
    "Crownbeard": (6000.0, 0.68, {"meadow": 0.35, "edge": 0.25, "montane": 0.15}),
    "Shamrock": (3000.0, 0.68, {"riparian": 0.6, "meadow": 0.25, "village": 0.35}),
    "Purslane": (2500.0, 0.68, {"village": 0.4, "montane": 0.2, "meadow": 0.1}),
    "Lachenalia": (3500.0, 0.76, {"meadow": 0.15, "montane": 0.2, "village": 0.2}),
    "Clover": (5000.0, 0.58, {"meadow": 0.45, "riparian": 0.4, "village": 0.4}),
    "CloverPatch": (7000.0, 0.7, {"meadow": 0.12, "village": 0.12}),
}
# the grass sward under the clumps: probability per carpet cell by community, and its species mix
CARPET = {"meadow": 0.9, "village": 0.8, "riparian": 0.85, "edge": 0.55, "montane": 0.35, "forest": 0.04, "rock": 0.0}
CARPET_MIX = [("WildGrass", 4.0), ("Kikuyu", 3.0), ("KikuyuSmall", 1.5)]
GROUND_ACCEPT = {"meadow": 0.95, "village": 0.75, "edge": 0.95, "forest": 0.95, "riparian": 0.95, "montane": 0.7,
                 "rock": 0.35}
ROCK_ACCEPT = {"rock": 0.85, "montane": 0.3, "forest": 0.12, "edge": 0.08, "riparian": 0.12, "meadow": 0.025,
               "village": 0.0}
DEBRIS_ACCEPT = {"forest": 0.32, "edge": 0.08, "riparian": 0.08, "montane": 0.05, "meadow": 0.006, "village": 0.0,
                 "rock": 0.02}
