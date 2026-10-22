import math

from pypcg.stages import w07_vegetation as S
from pypcg.world import MESH, scatter
from world_fixtures import Surface, run_stage, table, terrain

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def ground(x, y):
    return 1000.0 + (0.9 * (x - 8000.0) if x > 8000.0 else 0.0) + (0.15 * (x - 2000.0) if x > 2000.0 else 0.0)


def _inputs():
    road = table([{"loc": (-12000.0, y, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": y + 23000.0} for y in range(-23000, 23001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (-4000.0, y, 950.0), "Width": 1000.0, "WaterZ": 950.0, "BedZ": 800.0, "S": y + 23000.0}
                   for y in range(-23000, 23001, 1000)], WT, ["River"])
    return {"Terrain": [(terrain(ground), frozenset())], "Surface": [(Surface(ground), frozenset())],
            "Upstream": [road, river]}


def test_biomes_exclusions_and_grounding():
    out, _ = run_stage(S, _inputs(), Seed=3)
    s = out["Summary"][0][0].values
    assert s["trees"] > 100 and s["rocks"] > 0 and s["grass"] > 0
    assert s["alder_share_riparian"] > s["alder_share_all"]
    ex = scatter.Exclusions([([(-12000.0, -23000.0), (-12000.0, 23000.0)], 400.0)], [],
                            [(-4000.0, -23000.0, 950.0, 1000.0), (-4000.0, 23000.0, 950.0, 1000.0)], [])
    trees = out["Trees"][0][0]
    for (x, y, z) in trees.loc:
        assert ex.line_gap(x, y) >= 300.0 and ex.river_gap(x, y) >= 150.0
        assert abs(z - (ground(x, y) - 15.0)) < 1e-6
    rocks = out["Rocks"][0][0]
    assert all(x > 7500.0 for x, _y, _z in rocks.loc)


def test_deterministic():
    a, _ = run_stage(S, _inputs(), Seed=5)
    b, _ = run_stage(S, _inputs(), Seed=5)
    assert a["Trees"][0][0].loc == b["Trees"][0][0].loc


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Trees"] == [] and out["Summary"][0][0].values["trees"] == 0
