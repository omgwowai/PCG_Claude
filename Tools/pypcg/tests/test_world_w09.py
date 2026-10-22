from pypcg.geo import Polygon
from pypcg.stages import w09_surface as S
from pypcg.world import CHANNELS, MESH, geom, points as WP
from world_fixtures import run_stage, table, terrain

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def ground(x, y):
    return 1000.0 + (1.5 * (x - 15000.0) if x > 15000.0 else 0.0)


def test_channels():
    road = table([{"loc": (x, -10000.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (-15000.0, y, 950.0), "Width": 1200.0, "WaterZ": 950.0, "BedZ": 800.0, "S": y + 23000.0}
                   for y in range(-23000, 23001, 1000)], WT, ["River"])
    trees = (WP.mesh_points([((x, y, 1000.0), (0, 0, 0), (1, 1, 1), MESH["BeechA"])
                             for x in range(0, 6000, 400) for y in range(4000, 10000, 400)]), frozenset(["Tree"]))
    field = (Polygon(geom.rect(8000.0, -18000.0, 3000.0, 3000.0, 0.0), [], 1000.0), frozenset(["Field"]))
    out, _ = run_stage(S, {"Terrain": [(terrain(ground), frozenset())], "Upstream": [road, river, trees, field]})
    t = out["Terrain"][0][0]
    at = {(round(p[0]), round(p[1])): i for i, p in enumerate(t.loc)}

    def w(x, y):
        i = at[(round(x), round(y))]
        return {c: t.attrs[c][i] for c in CHANNELS}
    assert all(t.types[c] == "Float" for c in CHANNELS)
    assert w(0.0, -9960.9375)["Dirt"] > 0.9                           # on the road
    assert w(-14648.4375, 0.0)["Gravel"] > 0.9                        # river bed
    assert w(21094.0, 0.0)["Rock"] > 0.9                              # 56 degrees
    assert w(2930.0, 7031.0)["ForestFloor"] > 0.5
    assert w(-21094.0, 21094.0)["Grass"] > 0.99
    s = out["Summary"][0][0].values
    assert s["channels"] == 6 and s["weight_sum_err_max"] < 1e-6


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["channels"] == 0


def test_forest_floor_has_no_cell_edges():
    """Tree density counted per 20 m cell made square ForestFloor patches in the editor; the weight is interpolated
    between cell centres, so neighbouring vertices (5.86 m apart) differ by at most 0.35."""
    trees = (WP.mesh_points([((x, y, 1000.0), (0, 0, 0), (1, 1, 1), MESH["BeechA"])        # W7's forest density
                             for x in range(-12000, 12000, 1200) for y in range(-12000, 12000, 1200)]), frozenset(["Tree"]))
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0), frozenset())], "Upstream": [trees]})
    t = out["Terrain"][0][0]
    ff = {(round(p[0]), round(p[1])): t.attrs["ForestFloor"][i] for i, p in enumerate(t.loc)}
    s = 585.9375
    worst = 0.0
    for (x, y), v in ff.items():
        n = ff.get((round(x + s), y))
        if n is not None:
            worst = max(worst, abs(v - n))
    assert worst <= 0.35, worst
