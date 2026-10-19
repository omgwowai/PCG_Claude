"""Stage 2 -- BG_Buildings (PCG_1_2_BG_Buildings, 远景天际线).

Scatters the background skyline's building points over a square ring around the city: a 25 km square
minus a ~4.12 km centre square, one jittered point per ~1 km cell (1e-6 points per m2), each turned by
a random yaw, then a random cull keeps `KeepRatio` of them. The kept `SpawnAssets` node
(`Spawn_Assets`, 3 SM_bgcity meshes) turns the points into instances. Replaces the official graph's
six computation nodes: the two `Create_Spline_Shape` squares (`Subgraph_4`, `Subgraph_5`), the
`CreateConstant_0` size they share, `Compose_Areas_Exclusion` (`Exclude_Center`),
`Fill_Areas_Randomly` (`ScatterPoints`) and `Filter_RandomChoice` (`Subgraph_6`).
See docs/pypcg/stages/s02.md."""
import math

from pypcg import geo
from pypcg.geo import Points
from pypcg.stage_api import Param

STAGE = 2
DOC = """BG_Buildings (远景天际线): background skyline points on the square ring between an OuterSize
square and a CenterSize square, both centred on the world origin. The ring is cut into square cells of
1 / sqrt(PointsPerSquaredMeter) m and every cell gets one point at a random place in it (dropped when
that place is off the ring); every point gets a random yaw in +-MaxYaw degrees, and a random KeepRatio
of the points is kept. Sizes in cm."""
RANDOM = True
PARAMS = {
    "OuterSize": Param(2500000.0, "Side of the outer square, centred on the world origin (cm)", category="Area"),
    "CenterSize": Param(411769.84375, "Side of the centre square left empty for the city (cm); the official "
                                      "graph's CreateConstant_0 value, which overrides both its Width and Length",
                        category="Area"),
    "PointsPerSquaredMeter": Param(1e-06, "Sampling density: one cell of 1 / sqrt(density) m per point",
                                   category="Scatter"),
    "KeepRatio": Param(0.641598, "Share of the sampled points kept by the random cull", category="Scatter"),
    "MaxYaw": Param(180.0, "Each point is turned by a random yaw in [-MaxYaw, MaxYaw] degrees", category="Scatter"),
}
INPUTS = {}
OUTPUTS = ("Points",)

# Fixed inside the official primitives (Fill_Areas_Randomly defaults the graph does not override).
SAMPLING_EXTENTS = 1.0          # SamplingPointExtents (1, 1, 1): the sampler's own point half-size, cm
OUTPUT_EXTENTS = 10.0           # OutputPointsExtents (10, 10, 10): the published points' half-size, cm
STEEPNESS = 1.0                 # SurfaceSampler_1 PointSteepness
INT32 = 2 ** 31


def halves(params):
    """(outer half side, centre half side) in cm."""
    return float(params["OuterSize"]) / 2.0, float(params["CenterSize"]) / 2.0


def on_ring(x, y, outer, inner):
    """Inside the outer square and not strictly inside the centre square."""
    return abs(x) <= outer and abs(y) <= outer and not (abs(x) < inner and abs(y) < inner)


def cell_size(per_m2):
    """`FSurfaceSamplerData::Initialize` (non-legacy grid) with square extents: the cell side is
    sqrt(cm2 per point); the jitter square inside it is the cell minus twice the sampling extents
    (`Looseness` 1, so no inner offset). None when the density yields no point."""
    if not per_m2 > 0.0:
        return None
    size = math.sqrt((100.0 * 100.0) / per_m2)
    return max(size, 2.0 * SAMPLING_EXTENTS)


def cell_range(half, cell):
    """The engine's cell indices over [-half, half]: ceil(min / cell) .. floor(max / cell)."""
    return range(math.ceil(-half / cell), math.floor(half / cell) + 1)


def sample(params, rng):
    """`Fill_Areas_Randomly` over the ring: one candidate per cell, kept when it lands on the ring.
    Each candidate draws the cell's chance (it becomes the density, `bApplyDensityToPoints`) and then
    its X and Y in that order, as `SurfaceSampler_1` does; the yaw comes after (`TransformPoints_1`)."""
    pts = Points()
    outer, inner = halves(params)
    cell = cell_size(float(params["PointsPerSquaredMeter"]))
    if cell is None or not outer > 0.0 or inner >= outer:
        return pts
    jitter = cell - 2.0 * SAMPLING_EXTENTS
    max_yaw = abs(float(params["MaxYaw"]))
    cells = cell_range(outer, cell)
    for i in cells:
        for j in cells:
            chance = rng.random()
            x = i * cell + rng.random() * jitter
            y = j * cell + rng.random() * jitter
            if not on_ring(x, y, outer, inner):
                continue
            pts.add((x, y, 0.0), rot=(0.0, rng.uniform(-max_yaw, max_yaw), 0.0), density=1.0 - chance,
                    bounds_min=(-OUTPUT_EXTENTS,) * 3, bounds_max=(OUTPUT_EXTENTS,) * 3,
                    steepness=STEEPNESS, seed=rng.randrange(-INT32, INT32))
    return pts


def expected_sampled(params):
    """How many points `sample` publishes on average: the ring's area inside the cells' jitter
    squares, over one jitter square. Used by the tests and the V1 check, not by run()."""
    outer, inner = halves(params)
    cell = cell_size(float(params["PointsPerSquaredMeter"]))
    if cell is None or not outer > 0.0 or inner >= outer:
        return 0.0
    jitter = cell - 2.0 * SAMPLING_EXTENTS
    cells = list(cell_range(outer, cell))

    def cover(lo, hi):
        """Per-axis overlap of [lo, hi] with every jitter span, as a fraction of one span."""
        return [max(0.0, min(hi, i * cell + jitter) - max(lo, i * cell)) / jitter for i in cells]

    ox = cover(-outer, outer)
    ix = cover(-inner, inner)
    return sum(a * b for a in ox for b in ox) - sum(a * b for a in ix for b in ix)


def run(inputs, params, ctx):
    pts = sample(params, ctx.rng)
    ctx.notes.append("sampled %d" % len(pts))
    kept = pts.take(geo.choose(len(pts), float(params["KeepRatio"]), ctx.rng))
    return {"Points": [(kept, ["Points"])] if len(kept) else []}
