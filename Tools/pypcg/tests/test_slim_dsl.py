import copy
import types

import pytest

from pypcg import compare, dsl, host, ir as pir
from pypcg.stage_api import Param
from test_dsl import FAKE, PROFILE

STUB = types.SimpleNamespace(__name__="pypcg.stages.s06_districts", STAGE=6, DOC="Districts doc. ", RANDOM=True,
                             PARAMS={"Ratio": Param(0.5, "split ratio", category="Split")},
                             INPUTS={"City": "spline", "Arteries": "spline"}, OUTPUTS=("Areas", "Roads"))
OFFICIAL = {"graph": "/X/PCG_3_1_1_Districts.PCG_3_1_1_Districts", "params": [
    {"name": "Road_Profile", "type": "SoftObject", "value": "/P/SGD.SGD", "container": "None",
     "type_object": "/P/BP.BP_C", "category": "Road Parameters", "meta": {}}],
    "nodes": [{"name": "Subgraph_0", "class": "PCGSubgraphSettings", "title": "Get Roads",
               "subgraph": "/P/Get_ActorDataByRef.Get_ActorDataByRef",
               "overrides": {"ActorReferences": ["/Game/L.L:PersistentLevel.Roads"]}, "settings": {"Seed": 1}},
              {"name": "Spawn", "class": "PCGSubgraphSettings", "title": "Spawn Things",
               "subgraph": "/P/Filter_Tags.Filter_Tags", "overrides": {"FilteredInputTags": "A"},
               "settings": {"Seed": 2}, "pin_defaults": [{"index": 0, "type": "Double", "value": 1.0, "activated": True}]}]}


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(dsl, "_LIBRARY", copy.deepcopy(FAKE))       # library() adds classes; keep FAKE intact
    monkeypatch.setattr(dsl, "_official_ir", lambda stage: OFFICIAL)
    monkeypatch.setattr(dsl, "_role_by_path", lambda: {"/Game/L.L:PersistentLevel.Roads": "Roads"})


def _node(ir, cls):
    return [n for n in ir["nodes"] if n["class"] == cls]


def wire_all(g):
    """Feed every still-unwired input pin of the Python node from an actor read (a slim graph must
    wire them all: an unwired dynamic pin culls the node)."""
    wired = {p["label"] for p in g.py._rec["inputs"] if p["edges"]}
    for pin in g.py._rec["dynamic_pins"]["inputs"]:
        if pin not in wired:
            g.connect(g.actor_by_tag(pin), g.py, pin)
    return g


def test_slim_graph_declares_seed_and_params_and_wires_every_getter():
    out = wire_all(dsl.SlimGraph(STUB)).to_ir(PROFILE)
    assert out["graph"] == "PCG_3_1_1_Districts" and out["graph_props"]["Description"] == "Districts doc."
    assert [p["name"] for p in out["params"]] == ["Seed", "Ratio"]
    ratio = out["params"][1]
    assert ratio["tooltip"] == "split ratio" and ratio["category"] == "Split" and ratio["type"] == "Double"
    py = _node(out, pir.PYTHON_NODE)[0]
    assert py["settings"]["InlineScript"] == host.inline_script("s06_districts")
    assert py["settings"]["InputDynamicPins"] == ["Params", "City", "Arteries"]
    assert py["settings"]["OutputDynamicPins"] == ["Areas", "Roads"]
    params_pin = [p for p in py["inputs"] if p["label"] == "Params"][0]
    assert len(params_pin["edges"]) == 2
    assert {n["getter_param"] for n in _node(out, "PCGUserParameterGetSettings")} == {"Seed", "Ratio"}


def test_unwired_python_pin_is_refused():
    g = dsl.SlimGraph(STUB)
    g.connect(g.actor_by_tag("City"), g.py, "City")
    with pytest.raises(ValueError) as e:
        g.to_ir(PROFILE)
    assert "Arteries" in str(e.value)


def test_python_pins_are_checked():
    g = dsl.SlimGraph(STUB)
    with pytest.raises(KeyError):
        g.connect(g.p("Ratio"), g.py, "Nope")
    with pytest.raises(KeyError):
        g.py["Nope"]
    g.out(g.py["Areas"])


def test_getters_are_shared():
    g = dsl.SlimGraph(STUB)
    g.p("Ratio")
    g.p("Ratio")
    assert len(_node(wire_all(g).to_ir(PROFILE), "PCGUserParameterGetSettings")) == 2      # Seed + Ratio, no duplicate


def test_keep_copies_the_official_node_and_turns_actor_paths_into_roles():
    g = dsl.SlimGraph(STUB)
    roads = g.keep("Subgraph_0")
    g.connect(roads, g.py, "City")
    spawn = g.keep("Spawn", PrimaryInput=g.py["Areas"])
    out = wire_all(g).to_ir(PROFILE)
    by_title = {n["title"]: n for n in out["nodes"]}
    assert by_title["Get Roads"]["overrides"]["ActorReferences"] == [PROFILE.ROLES["Roads"]]
    assert "Seed" not in by_title["Get Roads"]["settings"]
    assert by_title["Spawn Things"]["overrides"] == {"FilteredInputTags": "A"}
    assert by_title["Spawn Things"]["pin_defaults"][0]["value"] == 1.0
    assert spawn.name in {n["name"] for n in out["nodes"]}
    with pytest.raises(KeyError):
        g.keep("NoSuchNode")


def test_official_param_copies_the_descriptor():
    p = dsl.official_param(7, "Road_Profile")
    assert p.ir["type"] == "SoftObject" and p.ir["type_object"] == "/P/BP.BP_C" and p.ir["category"] == "Road Parameters"


def test_self_point_reads_the_volume_transform():
    g = dsl.SlimGraph(STUB)
    g.connect(g.self_point(), g.py, "City")
    n = _node(wire_all(g).to_ir(PROFILE), pir.SELF_NODE)[0]
    assert n["settings"] == {"Mode": "GetSinglePoint"}


def test_slim_normalize_maps_exported_pins_to_labels_and_drops_seeds():
    described = wire_all(dsl.SlimGraph(STUB)).to_ir(PROFILE)
    exported = {**described, "nodes": []}
    for n in described["nodes"]:
        e = dict(n, settings=dict(n.get("settings") or {}), pos=[1, 2])
        if n["class"] == pir.PYTHON_NODE:
            for key in ("InputDynamicPins", "OutputDynamicPins"):
                e["settings"][key] = {"PinProperties": [{"Label": label, "AllowedTypes": {}} for label in n["settings"][key]]}
        e["settings"]["Seed"] = 123
        exported["nodes"].append(e)
    assert compare.slim_diff(exported, described) == []
    py = [n for n in exported["nodes"] if n["class"] == pir.PYTHON_NODE][0]
    py["settings"]["InlineScript"] = "changed"
    assert [d["field"] for d in compare.slim_diff(exported, described)] == ["settings.InlineScript"]
