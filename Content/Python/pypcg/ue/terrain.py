"""Editor only: heights of a PCG surface (e.g. a Get_MeshTerrain output) through the data's own
SamplePoint, which casts along the surface's query ray -- no physics and no collision (spec 2.2)."""
import unreal


class Terrain:
    """Stages see only height(x, y); the PCG data object stays inside this wrapper."""

    def __init__(self, data):
        self._data = data

    def height(self, x, y):
        """Surface z under (x, y), or None where the ray misses."""
        transform = unreal.Transform(unreal.Vector(x, y, 0.0), unreal.Rotator(), unreal.Vector(1.0, 1.0, 1.0))
        box = unreal.Box(unreal.Vector(-1.0, -1.0, -1.0), unreal.Vector(1.0, 1.0, 1.0))
        res = self._data.k2_sample_point(transform, box, None)
        # A bool UFUNCTION with an out parameter comes back as the bare point when the cast hits and as
        # None when it misses; the tuple and bare-bool branches stay as harmless guards for other bindings.
        if isinstance(res, tuple):
            ok, point = bool(res[0]), res[1]
        elif isinstance(res, unreal.PCGPoint):
            ok, point = True, res
        else:
            ok, point = bool(res), None
        return float(point.transform.translation.z) if ok and point is not None else None
