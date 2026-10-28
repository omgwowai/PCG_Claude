import math

from pypcg.geo import Polygon
from pypcg.stages import w07_vegetation as S
from pypcg.world import ecology, flora, geom, scatter
from world_fixtures import run_stage, table, terrain

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}
FIELD = geom.rect(-16000.0, 8000.0, 4000.0, 3000.0, 0.0)
HOUSE = geom.rect(-16000.0, 2000.0, 1000.0, 1000.0, 0.0)


def ground(x, y):
    return 1000.0 + 0.5 * min(max(x - 2000.0, 0.0), 10000.0) + (1.2 * (x - 12000.0) if x > 12000.0 else 0.0) \
        + 0.02 * y


def _inputs():
    road = table([{"loc": (-12000.0, y, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": y + 23000.0} for y in range(-23000, 23001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (-4000.0, y, 950.0), "Width": 1000.0, "WaterZ": 950.0, "BedZ": 800.0, "S": y + 23000.0}
                   for y in range(-23000, 23001, 1000)], WT, ["River"])
    areas = [(Polygon(list(FIELD), [], 1000.0), frozenset(["Field"])),
             (Polygon(list(HOUSE), [], 1000.0), frozenset(["Footprint"]))]
    return {"Terrain": [(terrain(ground), frozenset())], "Upstream": [road, river] + areas}


def _run(**kw):
    out, ctx = run_stage(S, _inputs(), Seed=3, **kw)
    return out, out["Summary"][0][0].values


def test_layers_richness_and_communities():
    out, s = _run()
    assert s["trees"] > 300 and s["shrubs"] > 100 and s["grass"] > 1000 and s["ground"] > 1000
    assert s["debris"] > 20 and s["rocks"] > 20
    assert s["species_used"] >= 30
    assert s["comm_forest"] > 0 and s["comm_edge"] > 0 and s["comm_meadow"] > 0 and s["comm_riparian"] > 0
    assert s["comm_rock"] > 0
    assert s["alder_share_riparian"] > s["alder_share_all"]
    for pin, tag in (("Trees", "Tree"), ("Shrubs", "Shrub"), ("Grass", "Grass"), ("Ground", "GroundPlant"),
                     ("Debris", "Debris"), ("Rocks", "Rock")):
        assert out[pin] and tag in out[pin][0][1]


def test_clearings():
    out, _s = _run()
    ex = scatter.Exclusions([([(-12000.0, -23000.0), (-12000.0, 23000.0)], 400.0)], [],
                            [(-4000.0, -23000.0, 950.0, 1000.0), (-4000.0, 23000.0, 950.0, 1000.0)],
                            [FIELD, HOUSE])
    for (x, y, _z) in out["Trees"][0][0].loc:
        assert ex.line_gap(x, y) >= 300.0 and ex.river_gap(x, y) >= 150.0 and not ex.rings.near(x, y, 300.0)
    for (x, y, _z) in out["Shrubs"][0][0].loc:
        assert ex.line_gap(x, y) >= 150.0 and not ex.rings.near(x, y, 150.0)
    for pin in ("Grass", "Ground"):
        for (x, y, _z) in out[pin][0][0].loc:
            assert ex.line_gap(x, y) >= 40.0 and not ex.rings.contains(x, y)


def test_trees_stand_on_the_ground_and_keep_apart():
    out, _s = _run()
    trees = out["Trees"][0][0]
    for (x, y, z), mesh in zip(trees.loc, trees.attrs["Mesh"]):
        if min(abs(x - 2000.0), abs(x - 12000.0)) > 600.0:
            assert abs(z - (ground(x, y) - flora.TREE_SINK[mesh])) < 1e-6
    pts = list(trees.loc)
    close = sum(1 for i in range(len(pts)) for j in range(i + 1, min(len(pts), i + 400))
                if math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) < 100.0)
    assert close == 0


def test_hedgerow_around_the_field():
    out, _s = _run()
    x0, y0, x1, y1 = -18000.0, 6500.0, -14000.0, 9500.0
    near = [p for pin in ("Shrubs", "Trees") for p in out[pin][0][0].loc
            if x0 - 400 < p[0] < x1 + 400 and y0 - 400 < p[1] < y1 + 400
            and not (x0 < p[0] < x1 and y0 < p[1] < y1)]
    assert len(near) >= 10


def test_densities_scale():
    _o, a = _run(GroundDensity=0.5, Density=0.5)
    _o, b = _run()
    assert a["ground"] < b["ground"] and a["trees"] < b["trees"]
    _o, c = _run(GrassDensity=0.0)
    assert c["grass"] == 0


def test_deterministic():
    a, _ = run_stage(S, _inputs(), Seed=5)
    b, _ = run_stage(S, _inputs(), Seed=5)
    for pin in ("Trees", "Ground", "Rocks"):
        assert a[pin][0][0].loc == b[pin][0][0].loc


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Trees"] == [] and out["Summary"][0][0].values["trees"] == 0


def _up(pitch, yaw, roll):
    """The Z axis of UE's FRotationMatrix for a rotator."""
    P, Y, R = (math.radians(v) for v in (pitch, yaw, roll))
    return (-(math.cos(R) * math.sin(P) * math.cos(Y) + math.sin(R) * math.sin(Y)),
            math.cos(Y) * math.sin(R) - math.cos(R) * math.sin(P) * math.sin(Y), math.cos(R) * math.cos(P))


def test_align_puts_the_up_axis_on_the_normal():
    for gx, gy, yaw in ((0.3, 0.0, 0.0), (0.0, -0.4, 0.0), (0.2, 0.35, 37.0), (-0.5, 0.1, 250.0)):
        up = _up(*ecology.align(yaw, gx, gy, 1.0))
        n = (-gx, -gy, 1.0)
        L = math.sqrt(sum(v * v for v in n))
        assert sum(a * b / L for a, b in zip(up, n)) > 0.9999
    assert ecology.align(10.0, 0.3, 0.2, 0.0) == (0.0, 10.0, 0.0)
