import pytest

from pypcg import ir, stage_api, world as W
from pypcg.world import checks, graphs


@pytest.mark.parametrize("n", range(1, 10))
def test_graph_description(n):
    out = graphs.graph(n).to_ir(None)                  # raises on an unwired Python input pin
    assert out["graph"] == W.name(n) and out["params"][0]["name"] == stage_api.SEED
    py = [x for x in out["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert len(py) == 1
    used = {(src, pin) for x in out["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    for pin in py[0]["settings"]["OutputDynamicPins"]:
        assert (py[0]["name"], pin) in used, pin
    getters = {x["getter_param"] for x in out["nodes"] if x.get("getter_param")}
    assert {p["name"] for p in out["params"]} <= getters


def _subs(n, alias):
    return [x for x in graphs.graph(n).to_ir(None)["nodes"] if (x.get("subgraph") or "").endswith(alias + "." + alias)]


def test_terrain_priorities():
    for n, (query, read_sub, write_sub) in W.TERRAIN.items():
        get = _subs(n, "Get_MeshTerrain")[0]["overrides"]
        assert get.get("MeshPartitionQueryType", "Base") == query and get.get("ModifierSubPriority", 0) == read_sub
        assert _subs(n, "Write_MeshTerrain")[0]["overrides"]["ModifierSubPriority"] == write_sub
    assert _subs(9, "Write_MeshTerrain")[0]["overrides"]["Channels"] == list(W.CHANNELS)
    for n in (2, 7, 8):
        assert _subs(n, "Get_MeshTerrain")[0]["overrides"]["MeshPartitionQueryType"] == "Final"


def test_acceptance_rules():
    good4 = {"connected": True, "unreachable": 0, "max_grade_main": 0.1, "max_grade_secondary": 0.13, "roads": 6}
    assert checks.accept(4, good4, {"instances": 10}) == []
    bad = dict(good4, connected=False, max_grade_main=0.2)
    assert len(checks.accept(4, bad, {"instances": 0})) == 3
    assert checks.accept(6, None, {}) == ["no Summary: the Python node did not run or its record is missing"]


def test_world_checks():
    roads = [{"cls": "Main", "width": 800.0, "pts": [(0.0, 0.0, 0.0), (1000.0, 0.0, 50.0)], "bridge": [False, False]},
             {"cls": "Secondary", "width": 500.0, "pts": [(500.0, 0.0, 25.0), (500.0, 900.0, 25.0)], "bridge": [False, False]}]
    river = [(-100.0, 500.0, 0.0, 600.0), (2000.0, 500.0, 0.0, 600.0)]
    assert checks.crossings(roads, river) == 1
    assert checks.roads_connected(roads, [(0.0, 0.0, 100.0), (500.0, 900.0, 100.0)])
    assert not checks.roads_connected(roads, [(5000.0, 5000.0, 100.0)])
    assert abs(checks.max_grades(roads)["Main"] - 0.05) < 1e-12


def test_river_acceptance_wants_round_bends_and_the_water_mesh():
    good3 = {"length_m": 2800.0, "monotone": True, "carved": 1500, "straight_share": 0.02, "max_turn_deg": 11.0}
    assert checks.accept(3, good3, {"instances": 0, "dynamic_meshes": 1}) == []
    assert len(checks.accept(3, dict(good3, straight_share=0.4), {"dynamic_meshes": 1})) == 1
    assert len(checks.accept(3, dict(good3, max_turn_deg=28.0), {"dynamic_meshes": 1})) == 1
    assert len(checks.accept(3, good3, {"instances": 266})) == 1          # the old planes are not a water surface
    assert any(n["class"] == "PCGSpawnDynamicMeshSettings" for n in graphs.graph(3).to_ir(None)["nodes"])


def test_w06_spawns_kit_modules_with_their_materials():
    """The template grammar nodes are gone: the modules go to one native mesh spawner that takes each point's mesh and
    its slot-0 material from attributes."""
    nodes = graphs.graph(6).to_ir(None)["nodes"]
    assert not [n for n in nodes if (n.get("subgraph") or "").endswith("Assign_ShapeGrammarDefinition")]
    sp = [n for n in nodes if n["class"] == "PCGStaticMeshSpawnerSettings"]
    assert len(sp) == 1
    sel = sp[0]["settings"]["MeshSelectorParameters"]
    assert sel["AttributeName"] == "Mesh" and sel["bUseAttributeMaterialOverrides"] is True
    assert sel["MaterialOverrideAttributes"] == ["Mat0"]


def test_town_acceptance():
    good = {"town_min": 80, "village_min": 30, "hamlet_min": 6, "churches_min": 1, "overlaps": 0, "on_road": 0,
            "styles": 7, "doors_front": 200, "buildings": 200, "bay_scale_min": 0.85, "bay_scale_max": 1.2,
            "attached": 30}
    assert checks.accept(6, good, {"instances": 10}) == []
    assert len(checks.accept(6, dict(good, styles=2), {"instances": 10})) == 1
    assert len(checks.accept(6, dict(good, doors_front=199), {"instances": 10})) == 1
    assert len(checks.accept(6, dict(good, attached=0), {"instances": 10})) == 1
