from pypcg import dsl, ir, level, world as W
from pypcg.stages import s00_probe


def test_stage_table():
    assert [s[0] for s in W.STAGES] == list(range(1, 10))
    assert W.name(4) == "PCGW_04_Roads"
    assert W.asset(4) == "/Game/PyPCG/World/PCGW_04_Roads"
    assert W.volume_tag(4) == "PyWorld_W04"
    assert W.TERRAIN[3] == ("Intermediate", 2, 3)
    assert level.WORLD == W.LEVEL == "/Game/PyPCG/L_PyWorld"
    assert all(p.count(".") == 1 for p in W.MESH.values())


def test_slim_graph_takes_a_name():
    g = dsl.SlimGraph(s00_probe, name="PCGW_Test")
    assert g.name == "PCGW_Test"


def test_actor_points_node():
    g = dsl.Graph("T")
    n = g.actor_points("PyWorld_Location", "Get Locations")
    rec = n._rec
    assert rec["class"] == ir.SELF_NODE
    sel = rec["settings"]["ActorSelector"]
    assert rec["settings"]["Mode"] == "GetSinglePoint"
    assert sel["ActorSelectionTag"] == "PyWorld_Location" and sel["bSelectMultiple"] is True


def test_a_mesh_is_a_stage_value_and_records_as_a_summary():
    import json
    from pypcg import geo, stage_api
    m = geo.Mesh([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (0.0, 100.0, 0.0)], [(0, 2, 1)], material="/Game/M.M")
    assert isinstance(m, stage_api.VALUE_TYPES)
    d = geo.to_json(m)
    assert d == {"kind": "mesh", "vertices": 3, "triangles": 1, "material": "/Game/M.M",
                 "bbox": [[0.0, 0.0, 0.0], [100.0, 100.0, 0.0]]}
    json.dumps(d)
