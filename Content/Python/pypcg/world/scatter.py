"""Jittered-grid scattering and the exclusion zones (视频步骤 7：区域遮罩 + 散布规则；沿路清空)."""
from pypcg.geo import Points, Polygon

from . import geom


def jittered(x0, y0, x1, y1, cell, rng):
    """One uniformly jittered point per cell of a grid over the box, row by row."""
    nx, ny = int((x1 - x0) // cell), int((y1 - y0) // cell)
    for j in range(ny):
        for i in range(nx):
            yield x0 + (i + rng.random()) * cell, y0 + (j + rng.random()) * cell


class Exclusions:
    """Roads and streets (with half widths), the river (with widths) and the rings to keep clear."""

    def __init__(self, roads, streets, river, rings):
        self.lines = geom.SegmentIndex(2000.0)
        for pts, hw in list(roads) + list(streets):
            self.lines.add_polyline([p[:2] for p in pts], hw)
        self.river = geom.SegmentIndex(2000.0)
        for a, b in zip(river, river[1:]):
            self.river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
        self.rings = geom.RingIndex()
        for r in rings:
            self.rings.add(r)

    def line_gap(self, x, y):
        hit = self.lines.nearest(x, y, 4000.0)
        return hit[0] - self.lines.payload(hit[1]) if hit else 1e9

    def river_gap(self, x, y):
        hit = self.river.nearest(x, y, 6000.0)
        return hit[0] - 0.5 * self.river.payload(hit[1]) if hit else 1e9

    def clear(self, x, y, line_margin, river_margin, ring_margin):
        return (self.line_gap(x, y) >= line_margin and self.river_gap(x, y) >= river_margin
                and not self.rings.near(x, y, ring_margin))


def upstream_exclusions(items):
    from pypcg.world import points as WP
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    from pypcg.stages.w05_bridges import bridge_rows
    roads = [(rd["pts"], 0.5 * rd["width"]) for rd in road_rows(items)]
    streets = [([r["loc"] for r in WP.rows_of(v)], 0.5 * WP.rows_of(v)[0]["Width"])
               for v, tags in items if isinstance(v, Points) and "Street" in tags and len(v)]
    river = [(r[0], r[1], r[2], r[3]) for r in river_rows(items)]
    rings = [v.outer for v, tags in items if isinstance(v, Polygon) and tags & {"Footprint", "Plaza", "Field"}]
    rings += [geom.rect(b["x"], b["y"], b["span"], b["width"] + 200.0, b["yaw"]) for b in bridge_rows(items)]
    return Exclusions(roads, streets, river, rings)
