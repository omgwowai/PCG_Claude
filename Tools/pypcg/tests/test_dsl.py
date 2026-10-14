import types

import pytest

from pypcg import compare, dsl
from pypcg.dsl import D, Graph, P, knob, sel

FAKE = {
    "subgraphs": {
        "Filter_Tags": {"path": "/P/Filter_Tags.Filter_Tags", "inputs": ["PrimaryInput", "Execution Dependency"],
                        "outputs": ["Selected", "Unselected"], "params": {"FilteredInputTags": "String"}},
        "Get_ActorDataByRef": {"path": "/P/Get_ActorDataByRef.Get_ActorDataByRef", "inputs": [],
                               "outputs": ["Out"], "params": {"ActorReferences": "SoftObject"}},
        "Get_ActorData": {"path": "/P/Get_ActorData.Get_ActorData", "inputs": [], "outputs": ["Out"],
                          "params": {"ActorTag": "Name"}},
    },
    "classes": {
        "PCGRerouteSettings": {"inputs": ["In"], "outputs": ["Out"]},
        "PCGNamedRerouteDeclarationSettings": {"inputs": ["In"], "outputs": ["Out", "InvisiblePin"]},
        "PCGNamedRerouteUsageSettings": {"inputs": ["In"], "outputs": ["Out"]},
        "PCGUserParameterGetSettings": {"inputs": [], "outputs": ["Ratio"]},
        "PCGGenericUserParameterGetSettings": {"inputs": [], "outputs": ["Out"]},
        "PCGMetadataMathsSettings": {"inputs": ["InA", "InB"], "outputs": ["Out"]},
    },
    "io": {"input_node_inputs": [], "input_node_outputs": ["In"], "output_node_inputs": ["Out"],
           "output_node_outputs": ["Out"]},
    "fresh_seeds": {},
}
PROFILE = types.SimpleNamespace(ROLES={"Roads": "/Game/L.L:PersistentLevel.Roads"}, KNOBS={"W": 5.0})


@pytest.fixture(autouse=True)
def fake_library(monkeypatch):
    monkeypatch.setattr(dsl, "_LIBRARY", dict(FAKE))


def small():
    g = Graph("G", params=[P("Ratio", "Double", 0.9)])
    with g.step(1, "取数"):
        roads = g.ref("Roads", "Get Roads")
        fp = g.sub("Filter_Tags", "Filter Road Footprints", set={"FilteredInputTags": "RoadFootprints"},
                   comment="only footprints", PrimaryInput=roads)
    with g.step(2, "输出"):
        lots = g.declare("Lots", fp.Selected)
        g.out(lots.use(), g.reroute(fp.Unselected))
    return g


def test_to_ir_shape_and_edges():
    ir = small().to_ir(PROFILE)
    by_title = {n["title"]: n for n in ir["nodes"]}
    f = by_title["Filter Road Footprints"]
    assert f["overrides"] == {"FilteredInputTags": "RoadFootprints"}
    assert f["inputs"] == [{"label": "PrimaryInput", "edges": [[by_title["Get Roads"]["name"], "Out"]]}]
    assert f["comment"] == "only footprints" and f["bubble_visible"] is True
    assert f["step"] == "1 取数" and f["src"].startswith("test_dsl.py:")
    out = [n for n in ir["nodes"] if n["name"] == "DefaultOutputNode"][0]
    assert len(out["inputs"][0]["edges"]) == 2


def test_role_resolution_and_sites():
    ir = small().to_ir(PROFILE)
    ref = [n for n in ir["nodes"] if n["title"] == "Get Roads"][0]
    assert ref["overrides"]["ActorReferences"] == ["/Game/L.L:PersistentLevel.Roads"]
    assert {s["kind"] for s in ir["sites"]} == {"role"}
    with pytest.raises(KeyError, match="no role"):
        small().to_ir(types.SimpleNamespace(ROLES={}, KNOBS={}))


def test_declaration_usage_records_node_ref_and_invisible_edge():
    ir = small().to_ir(PROFILE)
    decl = [n for n in ir["nodes"] if n["class"] == "PCGNamedRerouteDeclarationSettings"][0]
    use = [n for n in ir["nodes"] if n["class"] == "PCGNamedRerouteUsageSettings"][0]
    assert use["settings"]["Declaration"] == {"node_ref": decl["name"]}
    assert use["inputs"] == [{"label": "In", "edges": [[decl["name"], "InvisiblePin"]]}]
    assert use["title"] == "Lots"


def test_knob_default_and_override():
    def g():
        x = Graph("K")
        x.out(x.sub("Filter_Tags", "F", set={"FilteredInputTags": knob("W", 1.0)}).Selected)
        return x
    assert g().to_ir(types.SimpleNamespace(ROLES={}, KNOBS={}))["nodes"][2]["overrides"]["FilteredInputTags"] == 1.0
    ir = g().to_ir(PROFILE)
    assert ir["nodes"][2]["overrides"]["FilteredInputTags"] == 5.0
    assert ir["sites"] == [{"where": "n2.overrides.FilteredInputTags", "kind": "knob", "knob": "W"}]


def test_unknown_alias_is_refused():
    with pytest.raises(KeyError, match="Filter_Tagz"):
        Graph("G").sub("Filter_Tagz")


def test_unknown_param_lists_params():
    with pytest.raises(KeyError, match="FilteredInputTags"):
        Graph("G").sub("Filter_Tags", set={"FilterInputTags": "x"})


def test_unknown_input_pin_lists_real_pins():
    g = Graph("G")
    src = g.reroute(g.input.In)
    with pytest.raises(KeyError, match="PrimaryInput"):
        g.sub("Filter_Tags", "F", PrimaryInputs=src)


def test_unknown_output_pin_is_refused():
    g = Graph("G")
    f = g.sub("Filter_Tags", "F")
    with pytest.raises(KeyError, match="Selected"):
        g.out(f.Chosen)
    with pytest.raises(KeyError, match="Out"):
        g.out(f)          # Filter_Tags has no "Out"


def test_param_getter_and_pin_defaults():
    g = Graph("G", params=[P("Ratio", "Double", 0.9)])
    m = g.node("PCGMetadataMathsSettings", set={"Operation": "Set", "InputSource1": sel("$Position.Z")},
               defaults=[D(1, "Double", 2.0)], InA=g.param("Ratio").Ratio)
    g.out(m)
    ir = g.to_ir(PROFILE)
    maths = ir["nodes"][3]
    assert maths["pin_defaults"] == [{"index": 1, "type": "Double", "value": 2.0, "activated": True}]
    assert maths["settings"]["InputSource1"] == "PCGBegin($Position.Z)PCGEnd"
    assert ir["nodes"][2]["getter_param"] == "Ratio"
    with pytest.raises(KeyError, match="no parameter"):
        g.param("Nope")
    with pytest.raises(KeyError, match="Ratio"):
        g.param("Nope")


def test_param_getter_accepts_case_variant():
    g = Graph("G", params=[P("UseMegaplantsTrees", "Bool", False)])
    got = g.param("UseMegaPlantsTrees")
    ir = g.to_ir(PROFILE)
    node = [n for n in ir["nodes"] if n["name"] == got.name][0]
    assert node["getter_param"] == "UseMegaPlantsTrees"


def test_param_getter_output_pin_is_its_own_param():
    g = Graph("G", params=[P("Ratio", "Double", 0.9)])
    assert g.param("Ratio").Ratio is not None
    with pytest.raises(KeyError, match="Other"):
        g.param("Ratio").Other


def test_same_structure_compares_equal():
    assert compare.diff(small().to_ir(PROFILE), small().to_ir(PROFILE), {}) == []
