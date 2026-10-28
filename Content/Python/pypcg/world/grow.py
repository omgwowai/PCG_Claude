"""PyWorld vegetation layers on top of the ecological fields (ecology.py): rocks, canopy trees, shrubs, hedgerows,
dead wood, river banks and ground plants, each a list of (loc, rot, scale, mesh) rows. No unreal import."""
import math

from . import geom, noise
from .ecology import (CARPET, CARPET_MIX, DEBRIS_ACCEPT, GROUND_ACCEPT, GROUND_BASE, PATCHES, ROCK_ACCEPT, SHRUB_MIX, TREE_MIX, Spacing,
                      align, smooth, weighted)
from .flora import HEIGHT, SPECIES

LAYERS = ("tree", "shrub", "grass", "ground", "debris", "rock")
VERTEX_REACH = 420.0           # a sample is at most this far from its nearest vertex (585.9375 / sqrt 2)


class Grower:
    def __init__(self, fields, rng, seed):
        self.F, self.lat, self.ex, self.rng, self.seed = fields, fields.lat, fields.ex, rng, seed
        self.rows = {layer: [] for layer in LAYERS}
        self.counts = {}
        self.trees, self.shrubs = Spacing(1000.0, 700.0), Spacing(500.0, 200.0)
        self.mature = []
        self._patch = {}
        self.grass_share = 1.0          # GrassDensity: the share of grass clumps kept

    # ---- placement helpers
    def clear(self, x, y, k, line_m, river_m, ring_m):
        F, ex = self.F, self.ex
        if F.line[k] - VERTEX_REACH < line_m and ex.line_gap(x, y) < line_m:
            return False
        if F.riv[k] - VERTEX_REACH < river_m and ex.river_gap(x, y) < river_m:
            return False
        if F.ring[k] and ex.rings.near(x, y, ring_m):
            return False
        return True

    def put(self, name, x, y, yaw=None, scale=None, tilt=0.0):
        sp = SPECIES[name]
        g = self.lat.surface(x, y)
        if g is None:
            return None
        rng = self.rng
        z, gx, gy = g
        mesh = rng.choice(sp["meshes"])
        sc = scale if scale is not None else rng.uniform(*sp["scale"])
        yaw = rng.uniform(0.0, 360.0) if yaw is None else yaw
        pitch, yaw, roll = align(yaw, gx, gy, sp.get("align", 0.0))
        if tilt:
            pitch, roll = pitch + rng.uniform(-tilt, tilt), roll + rng.uniform(-tilt, tilt)
        if sp["layer"] == "rock":
            sink = HEIGHT[mesh] * sc * sp["sink"]
        else:
            sink = sp["sink"]
        self.rows[sp["layer"]].append(((x, y, z - sink), (pitch, yaw, roll), (sc, sc, sc), mesh))
        self.counts[name] = self.counts.get(name, 0) + 1
        return mesh, sc

    def clump(self, name, x, y, k, margins=(40.0, 20.0, 40.0), scale_mul=1.0):
        sp, rng = SPECIES[name], self.rng
        if sp["layer"] == "grass" and rng.random() >= self.grass_share:
            return 0
        lo, hi = sp.get("clump", (1, 1))
        spread = sp.get("spread", 0.0)
        n = 0
        for i in range(rng.randint(lo, hi)):
            if i == 0:
                px, py = x, y
            else:
                a, r = rng.uniform(0.0, 2.0 * math.pi), spread * math.sqrt(rng.random())
                px, py = x + r * math.cos(a), y + r * math.sin(a)
            if not self.clear(px, py, k, *margins):
                continue
            sc = rng.uniform(*sp["scale"]) * scale_mul
            if self.put(name, px, py, scale=sc):
                n += 1
        return n

    def patch(self, k, name):
        cache = self._patch.get(name)
        if cache is None:
            cache = self._patch[name] = {}
        v = cache.get(k)
        if v is None:
            scale = PATCHES[name][0]
            x, y = self.lat.xy(k)
            v = cache[k] = noise.value(x / scale, y / scale, self.seed + 300 + len(name) * 17 + ord(name[0]))
        return v

    # ---- layers
    def rocks(self, cells, density):
        rng, F = self.rng, self.F
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            c = F.comm[k]
            p = ROCK_ACCEPT[c] + (0.4 * smooth(20.0, 38.0, F.slope[k]) if c in ("montane", "forest", "edge") else 0.0)
            if rng.random() >= p * density:
                continue
            if c in ("rock", "montane"):
                main = "Crag" if rng.random() < 0.55 else "Boulder"
            elif c == "riparian":
                main = "Boulder" if rng.random() < 0.5 else "Rock"
            else:
                main = "Boulder" if rng.random() < 0.6 else "RockSlab"
            if not self.clear(x, y, k, 250.0, -100.0, 250.0):
                continue
            got = self.put(main, x, y, tilt=12.0)
            if not got:
                continue
            mesh, sc = got
            R = max(80.0, HEIGHT.get(mesh, 100.0) * sc * 1.3)
            self.trees.add(x, y, R)
            for _i in range(rng.randint(2, 6)):
                a, d = rng.uniform(0.0, 2.0 * math.pi), R * rng.uniform(0.9, 2.2) + 50.0
                px, py = x + d * math.cos(a), y + d * math.sin(a)
                kk = F.at(px, py)
                if kk is not None and self.clear(px, py, kk, 250.0, -100.0, 250.0):
                    self.put("Rock" if rng.random() < 0.75 else "RockSlab", px, py, tilt=15.0,
                             scale=rng.uniform(0.35, 0.9))
            for _i in range(rng.randint(5, 12)):
                a, d = rng.uniform(0.0, 2.0 * math.pi), R * 2.5 * math.sqrt(rng.random())
                px, py = x + d * math.cos(a), y + d * math.sin(a)
                kk = F.at(px, py)
                if kk is not None and self.clear(px, py, kk, 100.0, -50.0, 100.0):
                    self.put("Pebbles", px, py, scale=rng.uniform(1.5, 3.5))

    def canopy(self, cells, density):
        rng, F, seed = self.rng, self.F, self.seed
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            c, f = F.comm[k], F.forest[k]
            if c == "forest":
                p = 0.9
                if rng.random() < 0.12 + 0.35 * (1.0 - f):
                    mix = "young"
                else:
                    mix = "forest_moist" if F.moist[k] > 0.5 else "forest"
            elif c == "edge":
                p, mix = 0.1 + 0.35 * f, "edge"
            elif c == "riparian":
                band = smooth(0.35, 0.6, noise.value(x / 7000.0, y / 7000.0, seed + 201))
                p, mix = (0.12 + 0.55 * band if F.riv[k] < 2500.0 else 0.25), "riparian"
            elif c == "montane":
                p, mix = 0.05 + 0.5 * f, "montane"
            elif c == "meadow":
                grove = smooth(0.72, 0.84, noise.value(x / 9000.0, y / 9000.0, seed + 211))
                p, mix = 0.0025 + 0.3 * grove, ("edge" if grove > 0.5 else "meadow")
            elif c == "village":
                p, mix = 0.012, "village"
            else:
                p, mix = 0.03, "rock"
            if rng.random() >= p * density:
                continue
            self.tree(weighted(rng, TREE_MIX[mix]), x, y, k, c)

    def tree(self, name, x, y, k, c, scale_mul=1.0):
        r = SPECIES[name]["space"] * scale_mul
        if not self.trees.free(x, y, r, 0.65):
            return False
        if not self.clear(x, y, k, 300.0 + 0.3 * r, 150.0, 300.0):
            return False
        sc = self.rng.uniform(*SPECIES[name]["scale"]) * scale_mul
        if not self.put(name, x, y, scale=sc):
            return False
        self.trees.add(x, y, r)
        if r >= 300.0 and c in ("forest", "edge", "riparian"):
            self.mature.append((x, y, k, sc))
        return True

    def understory(self, cells, density):
        rng, F, seed = self.rng, self.F, self.seed
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            c = F.comm[k]
            if c == "edge":
                p = 0.55 * F.edgeness(k)
            elif c == "forest":
                p = 0.12 if not self.trees.nearest_within(x, y, 450.0) else 0.015
            elif c == "riparian":
                p = 0.22
            elif c == "meadow":
                p = 0.003 + 0.2 * smooth(0.72, 0.84, noise.value(x / 9000.0, y / 9000.0, seed + 211))
            elif c == "village":
                p = 0.025
            elif c == "montane":
                p = 0.05
            else:
                p = 0.01
            if rng.random() >= p * density:
                continue
            self.shrub(weighted(rng, SHRUB_MIX[c if c in SHRUB_MIX else "montane"]), x, y, k)

    def shrub(self, name, x, y, k):
        r = SPECIES[name]["space"]
        if not self.shrubs.free(x, y, r, 0.6) or self.trees.nearest_within(x, y, 120.0):
            return False
        if not self.clear(x, y, k, 150.0, 50.0, 150.0):
            return False
        if self.put(name, x, y):
            self.shrubs.add(x, y, r)
            return True
        return False

    def tree_floor(self):
        """Roots, leaf litter and ivy around the mature trees of forests, edges and banks."""
        rng = self.rng
        for x, y, k, sc in self.mature:
            if rng.random() < 0.16:
                self.put("Roots", x, y, scale=sc * rng.uniform(0.6, 0.9))
            if rng.random() < 0.3:
                a, d = rng.uniform(0.0, 2.0 * math.pi), rng.uniform(80.0, 250.0)
                self.clump("Leaves", x + d * math.cos(a), y + d * math.sin(a), k)
            if rng.random() < 0.12:
                self.clump("Ivy", x, y, k)
            if rng.random() < 0.03:
                a = rng.uniform(0.0, 360.0)
                d = 30.0 * sc
                self.put("ClimbingIvy", x + d * math.cos(math.radians(a)), y + d * math.sin(math.radians(a)), yaw=a)

    def debris(self, cells, density):
        rng, F, lat = self.rng, self.F, self.lat
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            c = F.comm[k]
            p = DEBRIS_ACCEPT[c] * (F.forest[k] if c == "forest" else 1.0)
            if rng.random() >= p * density:
                continue
            kind = weighted(rng, [("Log", 0.22 if F.slope[k] < 28.0 else 0.0), ("Stump", 0.2), ("Branch", 0.35),
                                  ("Twigs", 0.23)])
            if kind == "Log":
                g = lat.surface(x, y)
                if g is None:
                    continue
                yaw = math.degrees(math.atan2(g[2], g[1])) + 90.0 + rng.uniform(-30.0, 30.0)
                dx, dy = math.cos(math.radians(yaw)) * 350.0, math.sin(math.radians(yaw)) * 350.0
                if any(self.trees.nearest_within(x + t * dx, y + t * dy, 150.0) for t in (-1.0, 0.0, 1.0)):
                    continue
                if all(self.clear(x + t * dx, y + t * dy, k, 300.0, 150.0, 300.0) for t in (-1.0, 0.0, 1.0)):
                    self.put("Log", x, y, yaw=yaw)
            elif kind == "Stump":
                if not self.trees.nearest_within(x, y, 150.0) and self.clear(x, y, k, 250.0, 100.0, 250.0):
                    self.put("Stump", x, y)
            else:
                self.clump(kind, x, y, k, margins=(100.0, 50.0, 100.0))

    def river_banks(self, river, step=150.0):
        """Pebbles and stones along both banks (river rows (x, y, water z, width))."""
        rng, F = self.rng, self.F
        for a, b in zip(river, river[1:]):
            L = geom.dist2d(a, b)
            if L <= 0.0:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            for i in range(int(L // step)):
                t = (i + rng.random()) * step / L
                w = 0.5 * (a[3] + (b[3] - a[3]) * t)
                for side in (-1.0, 1.0):
                    off = side * (w + rng.uniform(-120.0, 80.0))
                    x, y = a[0] + (b[0] - a[0]) * t - uy * off, a[1] + (b[1] - a[1]) * t + ux * off
                    k = F.at(x, y)
                    if k is None or not self.clear(x, y, k, 150.0, -200.0, 150.0):
                        continue
                    u = rng.random()
                    if u < 0.2:
                        self.clump("Pebbles", x, y, k, margins=(100.0, -200.0, 100.0))
                    elif u < 0.36:
                        self.put("Rock", x, y, tilt=15.0, scale=rng.uniform(0.35, 0.8))

    def hedgerows(self, fields, roads, step=250.0):
        """Shrub lines with a tree every so often around the fields and along the roads through open land."""
        rng, F, seed = self.rng, self.F, self.seed
        lines = []
        for idx, ring in enumerate(fields):
            cx, cy = geom.centroid(ring)
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                L = geom.dist2d(a, b)
                if L <= 0.0:
                    continue
                nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
                mx, my = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy
                if nx * mx + ny * my < 0.0:
                    nx, ny = -nx, -ny
                lines.append(([(a[0] + nx * 160.0, a[1] + ny * 160.0), (b[0] + nx * 160.0, b[1] + ny * 160.0)],
                              seed + 400 + idx, 0.3, False))
        for rid, (pts, hw) in enumerate(roads):
            for side in (-1.0, 1.0):
                off, out = side * (hw + 800.0), []
                for i in range(len(pts) - 1):
                    a, b = pts[i], pts[i + 1]
                    L = geom.dist2d(a, b)
                    if L > 0.0:
                        out.append((a[0] - (b[1] - a[1]) / L * off, a[1] + (b[0] - a[0]) / L * off))
                lines.append((out, seed + 500 + 2 * rid + (side > 0), 0.55, True))
        for pts, nseed, thr, road in lines:
            s = 0.0
            for a, b in zip(pts, pts[1:]):
                L = geom.dist2d(a, b)
                for i in range(int(L // step) + 1):
                    t = min(1.0, i * step / L) if L > 0.0 else 0.0
                    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                    s += step
                    if noise.value(s / 4000.0, 0.5, nseed) < thr:
                        continue
                    k = F.at(x, y)
                    if k is None or F.slope[k] > 15.0:
                        continue
                    if road and (F.comm[k] not in ("meadow", "village") or F.bld[k] < 2500.0):
                        continue
                    jx, jy = x + rng.uniform(-60.0, 60.0), y + rng.uniform(-60.0, 60.0)
                    if rng.random() < 0.12:
                        self.tree(weighted(rng, TREE_MIX["hedge"]), jx, jy, k, "hedge", 0.75)
                    elif rng.random() < 0.85:
                        self.shrub(weighted(rng, SHRUB_MIX["hedge"]), jx, jy, k)
                    if rng.random() < 0.6:
                        self.clump("WildGrass" if rng.random() < 0.7 else "Crownbeard", jx, jy, k)

    def ground(self, cells, density):
        rng, F = self.rng, self.F
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            c = F.comm[k]
            if rng.random() >= GROUND_ACCEPT[c] * density:
                continue
            name = self.pick_ground(k, c)
            if name is None:
                continue
            self.clump(name, x, y, k)

    def carpet(self, cells, density):
        """One grass plant per fine cell over open land: the continuous sward the clumps sit in."""
        rng, F = self.rng, self.F
        for x, y in cells:
            k = F.at(x, y)
            if k is None:
                continue
            p = CARPET.get(F.comm[k], 0.0) * (1.0 - smooth(18.0, 30.0, F.slope[k]))
            if p <= 0.0 or rng.random() >= p * density or rng.random() >= self.grass_share:
                continue
            if not self.clear(x, y, k, 60.0, 30.0, 60.0):
                continue
            self.put(weighted(rng, CARPET_MIX), x, y, scale=rng.uniform(1.0, 1.6))

    def pick_ground(self, k, c):
        rng, F = self.rng, self.F
        if F.line[k] < 350.0:
            return weighted(rng, [("Purslane", 1.0), ("KikuyuSmall", 2.0), ("Kikuyu", 1.0), (None, 1.0)])
        w = []
        for name, (_scale, thr, suit) in PATCHES.items():
            su = suit.get(c)
            if su:
                a = smooth(thr, thr + 0.12, self.patch(k, name)) * su
                if a > 0.0:
                    w.append((name, a))
        total = sum(a for _n, a in w)
        if total > 0.0 and rng.random() < min(0.45, 0.7 * total):
            return weighted(rng, w)
        if c == "riparian" and F.riv[k] < 300.0 and rng.random() < 0.25:
            return "Pebbles"
        return weighted(rng, GROUND_BASE[c])
