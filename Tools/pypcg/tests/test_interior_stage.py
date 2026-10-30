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


# ---------------------------------------------------------------- multi-storey houses (spec 2026-10-29)

BOX = [(0, 0), (1000, 0), (1000, 800), (0, 800)]


def inputs_floors(outlines, loc=(0.0, 0.0, 0.0), yaw=0.0, zs=None):
    """The stage's inputs for a house actor at `loc` turned `yaw` with one spline per local outline, outline k raised
    zs[k] (k x 300 by default) above the actor."""
    from test_interior_footprint import world_of
    zs = zs or [k * 300.0 for k in range(len(outlines))]
    vol = Points()
    vol.add(tuple(loc), rot=(0.0, yaw, 0.0), scale=(1.0, 1.0, 1.0))
    sp = [(Spline([(x, y, z + dz) for x, y, z in world_of(o, loc, yaw)], closed=True, linear=True), [])
          for o, dz in zip(outlines, zs)]
    return {"Footprint": sp, "Volume": [(vol, [])]}


def run_stage(ins, **params):
    return stage_api.execute(i01_house, ins, dict(stage_api.defaults(i01_house), Seed=1, **params), None)[0]


def test_stage_runs_a_two_storey_house():
    from pypcg.interior import stairs as ST
    out = run_stage(inputs_floors([BOX, BOX]))
    s = out["Summary"][0][0].values
    rooms = out["Rooms"][0][0]
    assert s["floors"] == 2 and s["failures"] == 0 and set(rooms.attrs["Floor"]) == {0, 1}, s
    assert s["stair"] in ST.TYPES and s["program"].count("/") == 1 and len(out["Parts"][0][0]) > 300
    assert len(rooms) == s["rooms"] + s["terraces"]


def test_stage_odd_spline_sets():
    """Review Focus 4: odd inputs give today's single-floor house or a reported note, never another single-floor house."""
    from test_interior_regression import digest
    one = run_stage(inputs_floors([BOX]))
    ref = digest(one)
    assert one["Summary"][0][0].values["floors"] == 1 and set(one["Rooms"][0][0].attrs["Floor"]) == {0}
    # Floors 1 with two splines: the ground floor's alone, the other reported
    a = run_stage(inputs_floors([BOX, BOX]), Floors=1)
    assert digest(a) == ref and "ignored" in a["Summary"][0][0].values["notes"]
    # a spline below the actor: it is the ground floor, reported
    b = run_stage(inputs_floors([BOX], zs=[-300.0]))
    assert digest(b) == ref and "below" in b["Summary"][0][0].values["notes"]
    # two splines on one level: the larger, reported
    c = run_stage(inputs_floors([BOX, [(0, 0), (600, 0), (600, 500), (0, 500)]], zs=[0.0, 0.0]))
    assert digest(c) == ref and "largest" in c["Summary"][0][0].values["notes"]


def test_stage_reports_a_dropped_floor():
    """An upper floor no stair can serve: the house is planned on one floor, the floor that went is reported."""
    small = [(0, 0), (600, 0), (600, 600), (0, 600)]
    out = run_stage(inputs_floors([small, small]))
    s = out["Summary"][0][0].values
    assert s["floors"] == 1 and s["dropped"] and s["failures"] == 0


def test_show_floors_param():
    every = run_stage(inputs_floors([BOX, BOX]))
    ground = run_stage(inputs_floors([BOX, BOX]), ShowFloors=1)
    assert 0 < len(ground["Parts"][0][0]) < len(every["Parts"][0][0])
    assert max(z for _x, _y, z in ground["Parts"][0][0].loc) <= 270.0 + 1e-6


def test_graph_description_has_the_new_params():
    names = {p["name"] for p in IG.house().to_ir(None)["params"]}
    assert {"Floors", "ShowFloors", "StairType"} <= names


def test_the_deck_material_is_made():
    """The terrace deck's floor material is one pyinterior_materials.py makes (FLOOR_MATERIALS, its FLOORS table)."""
    import os
    from pypcg.interior import program as P
    from pypcg.interior import terrace as T
    assert T.DECK_MATERIAL in P.FLOOR_MATERIALS
    src = open(os.path.join(os.path.dirname(i01_house.__file__), "..", "..", "pyinterior_materials.py"), encoding="utf-8").read()
    assert '"%s":' % T.DECK_MATERIAL in src
