"""Offline stand-ins for the editor services a stage reaches through ctx.ops (ruling N2)."""
from pypcg import geo


def _half(ring, a, b, side):
    def s(p):
        return side * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
    out = []
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        sp, sq = s(p), s(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


class FakeOps:
    """cut_with_paths for convex rings and straight paths (the line through each path's ends), and
    intersection of convex rings (Sutherland-Hodgman)."""

    def cut_with_paths(self, ring, paths):
        pieces = [list(ring)]
        for path in paths:
            a, b = path[0], path[-1]
            nxt = []
            for r in pieces:
                for side in (1, -1):
                    part = _half(r, a, b, side)
                    if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                        nxt.append(geo.ccw(part))
            pieces = nxt
        return pieces

    def intersection(self, rings_a, rings_b):
        out = []
        for a in rings_a:
            for b in rings_b:
                part, b = list(geo.ccw(a)), geo.ccw(b)
                for i in range(len(b)):
                    part = _half(part, b[i], b[(i + 1) % len(b)], 1) if len(part) >= 3 else []
                if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                    out.append(geo.Polygon(geo.ccw(part)))
        return out


class FlatTerrain:
    """A surface at constant height."""

    def __init__(self, z=0.0):
        self.z = z

    def height(self, x, y):
        return self.z
