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
