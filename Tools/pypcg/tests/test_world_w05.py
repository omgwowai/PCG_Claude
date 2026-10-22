from pypcg.stages import w05_bridges as S
from pypcg.world import MESH
from world_fixtures import run_stage, table

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def test_one_crossing_one_bridge():
    road = table([{"loc": (x, 0.0, 1200.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": abs(x) < 900,
                   "S": x + 5000.0} for x in range(-5000, 5001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (0.0, y, 900.0), "Width": 1600.0, "WaterZ": 900.0, "BedZ": 750.0, "S": y + 5000.0}
                   for y in range(-5000, 5001, 1000)], WT, ["River"])
    out, _ = run_stage(S, {"Upstream": [road, river]})
    s = out["Summary"][0][0].values
    assert s["bridges"] == s["crossings"] == 1
    b = S.bridge_rows(out["Bridges"])[0]
    assert abs(b["span"] - (1600.0 + 1200.0)) < 1e-6 and abs(b["x"]) < 1e-6
    meshes = out["Parts"][0][0].attrs["Mesh"]
    assert meshes.count(MESH["Cube"]) == 3 and meshes.count(MESH["Rail"]) == 14 and meshes.count(MESH["Cylinder"]) == 1


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Bridges"] == [] and out["Summary"][0][0].values["bridges"] == 0
