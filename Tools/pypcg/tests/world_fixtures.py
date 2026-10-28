"""Small synthetic inputs for the PyWorld stage tests."""
from pypcg import stage_api
from pypcg.geo import Points
from pypcg.world import VERTEX_CM


def terrain(fn, half=40, s=VERTEX_CM):
    """A (2*half+1)^2 vertex lattice centred on the origin, z = fn(x, y), carrying SourcePositions like the
    engine's Extract_MeshTerrainPoints."""
    p = Points()
    p.declare("SourcePositions", "Vector")
    for j in range(-half, half + 1):
        for i in range(-half, half + 1):
            x, y = i * s, j * s
            p.add((x, y, float(fn(x, y))), SourcePositions=(x, y, -600.0))
    return p


class Surface:
    """Stands in for the engine's terrain surface (pypcg.ue.terrain.Terrain)."""

    def __init__(self, fn, half_cm=None):
        self.fn, self.half = fn, half_cm

    def height(self, x, y):
        if self.half is not None and (abs(x) > self.half or abs(y) > self.half):
            return None
        return float(self.fn(x, y))


def table(rows, types, tags=()):
    from pypcg.world import points as WP
    return (WP.table_points(rows, types), frozenset(tags))


def run_stage(module, inputs, **params):
    p = stage_api.defaults(module)
    p.update(params)
    for pin in module.INPUTS:
        inputs.setdefault(pin, [])
    outputs, ctx = stage_api.execute(module, inputs, p, None)
    return outputs, ctx
