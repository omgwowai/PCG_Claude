"""PyInterior stage I1: the whole chain run through stage_api on the demo houses; the graph description."""
import pytest

from pypcg import ir, stage_api
from pypcg.geo import Points, Spline
from pypcg.interior import demo, graphs as IG
from pypcg.stages import i01_house


def inputs_for(shape, loc, yaw):
    pts = demo.world_points(shape, loc, yaw)
    vol = Points()
    vol.add(tuple(loc), rot=(0.0, yaw, 0.0), scale=(1.0, 1.0, 1.0))
    return {"Footprint": [(Spline(pts, closed=True, linear=True), [])], "Volume": [(vol, [])]}


@pytest.mark.parametrize("name, shape, loc, yaw, style, seed", demo.houses())
def test_demo_houses_run_clean(name, shape, loc, yaw, style, seed):
    params = dict(stage_api.defaults(i01_house), Style=style, Seed=seed)
    out, ctx = stage_api.execute(i01_house, inputs_for(shape, loc, yaw), params, None)
    parts = out["Parts"][0][0]
    rooms = out["Rooms"][0][0]
    summary = out["Summary"][0][0].values
    assert summary["failures"] == 0, summary
    assert len(parts) > 100 and len(rooms) == summary["rooms"]
    assert summary["windows"] > 0 and summary["items"] > 5
    assert set(rooms.attrs) >= {"Type", "Label", "Area", "Parent", "Windows", "Items"}
    # every part sits inside the house's outline (with the foundation's footprint) in world space
    xs, ys = [p[0] for p in demo.world_points(shape, loc, yaw)], [p[1] for p in demo.world_points(shape, loc, yaw)]
    for x, y, _z in parts.loc:
        assert min(xs) - 1.0 <= x <= max(xs) + 1.0 and min(ys) - 1.0 <= y <= max(ys) + 1.0


@pytest.mark.parametrize("yaw", [0.0, 120.0])
def test_rooms_carry_their_clear_size(yaw):
    """SizeX / SizeY: the room's clear rectangle in the house's frame (cm), centred on the room point -- what a camera
    standing in the room needs (pyinterior.py shot view "room")."""
    import math
    loc = (500.0, -300.0, 0.0)
    out, _ctx = stage_api.execute(i01_house, inputs_for("threebed", loc, yaw),
                                  dict(stage_api.defaults(i01_house), Seed=4), None)
    rooms = out["Rooms"][0][0]
    pts = demo.world_points("threebed", loc, yaw)
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    lx = [(p[0] - loc[0]) * ex[0] + (p[1] - loc[1]) * ex[1] for p in pts]
    ly = [(p[0] - loc[0]) * ey[0] + (p[1] - loc[1]) * ey[1] for p in pts]
    for i in range(len(rooms)):
        sx, sy = rooms.attrs["SizeX"][i], rooms.attrs["SizeY"][i]
        assert sx > 50.0 and sy > 50.0
        assert sx * sy / 1e4 == pytest.approx(rooms.attrs["Area"][i], abs=0.01)
        cx = (rooms.loc[i][0] - loc[0]) * ex[0] + (rooms.loc[i][1] - loc[1]) * ex[1]
        cy = (rooms.loc[i][0] - loc[0]) * ey[0] + (rooms.loc[i][1] - loc[1]) * ey[1]
        assert min(lx) <= cx - sx / 2 and cx + sx / 2 <= max(lx) + 1e-6
        assert min(ly) <= cy - sy / 2 and cy + sy / 2 <= max(ly) + 1e-6


def test_program_override_and_furnish_switch():
    base = dict(stage_api.defaults(i01_house), Seed=1)
    ins = inputs_for("threebed", (0.0, 0.0, 0.0), 0.0)
    auto = stage_api.execute(i01_house, ins, base, None)[0]["Summary"][0][0].values
    two = stage_api.execute(i01_house, ins, dict(base, Program="TwoBed"), None)[0]["Summary"][0][0].values
    bare = stage_api.execute(i01_house, ins, dict(base, Furnish=False), None)[0]["Summary"][0][0].values
    assert auto["program"] == "ThreeBed" and two["program"] == "TwoBed" and bare["items"] == 0


def test_no_footprint_publishes_nothing():
    vol = Points()
    vol.add((0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0))
    out, _ctx = stage_api.execute(i01_house, {"Footprint": [], "Volume": [(vol, [])]},
                                  dict(stage_api.defaults(i01_house)), None)
    assert out["Parts"] == [] and out["Summary"][0][0].values["error"]


def test_a_footprint_no_program_fits_publishes_only_an_error(monkeypatch):
    """When even the studio does not fit (here: its rooms made larger than the house), the stage publishes the error
    Summary and nothing else -- not one undivided room that fails every check (review finding 2)."""
    from dataclasses import replace
    from pypcg.interior import program as P
    monkeypatch.setitem(P.ROOMS, "Main", replace(P.ROOMS["Main"], min_short=900.0, min_long=900.0))
    out, _ctx = stage_api.execute(i01_house, inputs_for("studio", (0.0, 0.0, 0.0), 0.0),
                                  dict(stage_api.defaults(i01_house), Seed=1), None)
    summary = out["Summary"][0][0].values
    assert out["Parts"] == [] and out["Rooms"] == []
    assert summary["failures"] == 1 and "studio" in summary["error"]


def test_graph_description():
    out = IG.house().to_ir(None)                       # raises on an unwired Python input pin (trap 80)
    assert out["graph"] == "PCGI_House" and out["params"][0]["name"] == stage_api.SEED
    py = [x for x in out["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert len(py) == 1
    classes = {x["class"] for x in out["nodes"]}
    assert "PCGGetSplineSettings" in classes and "PCGStaticMeshSpawnerSettings" in classes
    getters = {x["getter_param"] for x in out["nodes"] if x.get("getter_param")}
    assert {p["name"] for p in out["params"]} <= getters
