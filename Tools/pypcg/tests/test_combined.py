"""The merged city graph (pypcg.combined): one PCG graph holding all 18 slim stage graphs."""
import pytest

from pypcg import combined, graphs, ir as _ir, stage_api, stages
from pypcg.profiles import official


@pytest.fixture(scope="module")
def g():
    return combined.build()


def test_every_stage_node_is_kept(g):
    """Every non-IO node of every slim graph appears once, under its stage prefix."""
    names = {rec["name"] for rec in g._nodes}
    for n in range(1, 19):
        part = graphs.graph(n)
        for rec in part._nodes:
            if rec["name"] not in _ir.IO_NODES:
                assert "s%02d_%s" % (n, rec["name"]) in names
    assert len(g._nodes) == sum(len(graphs.graph(n)._nodes) - 2 for n in range(1, 19)) + 2


def test_parameters_are_prefixed_and_grouped(g):
    names = [p.name for p in g._params]
    assert len(names) == len(set(names))
    for p in g._params:
        n = int(p.name[1:3])
        assert p.name.startswith("S%02d_" % n)
        assert p.ir["category"].split("|")[0] == combined.category(n)
    # every getter reads a declared, prefixed parameter
    declared = {x.lower() for x in names}
    for rec in g._nodes:
        if rec.get("getter_param"):
            assert rec["getter_param"].lower() in declared


def test_no_actor_reference_is_left(g):
    """Reads of another stage's volume become Gathers fed by that stage's output; the control-actor references
    become tag reads, so the graph names no actor of any level and runs in every level carrying the tags."""
    ir = g.to_ir(official)
    assert ir["sites"] == []
    for n in ir["nodes"]:
        assert "ActorReferences" not in (n.get("overrides") or {}), n["title"]
    tagged = {(x[0], x[3]) for x in g.report["refs_tagged"]}
    assert tagged == {(8, "Highway"), (9, "LandmarkPark"), (10, "LandmarkPark"), (13, "LandmarkPark")}
    for rec in g._nodes:
        if rec.get("subgraph") and rec["subgraph"].endswith("Get_ActorData.Get_ActorData"):
            assert set(rec["overrides"]) == {"ActorTag"}


def test_rewired_reads_carry_their_stage_outputs(g):
    by = {rec["name"]: rec for rec in g._nodes}
    for n, title, ups in g.report["refs_rewired"]:
        rec = next(r for r in g._nodes if r.get("title") == "[%02d] %s" % (n, title))
        assert rec["class"] == "PCGGatherSettings"
        edges = [tuple(e) for p in rec["inputs"] for e in p["edges"]]
        assert edges == [tuple(e) for u in ups for e in g.stage_outputs[u]]
        assert all(e[0] in by for e in edges)
        assert all(u < n for u in ups)


def test_self_reads_become_tagged_control_actor_reads(g):
    selfs = [rec for rec in g._nodes if rec["class"] == _ir.SELF_NODE]
    assert sorted(int(r["name"][1:3]) for r in selfs) == [4, 5]
    for r in selfs:
        sel = r["settings"]["ActorSelector"]
        assert sel["ActorSelection"] == "ByTag"
        assert sel["ActorSelectionTag"] == combined.CONTROL_TAGS[int(r["name"][1:3])]


def test_terrain_access_keeps_stage_order(g):
    """Each terrain query waits on every earlier stage's terrain writes, each write on every earlier query."""
    by = {rec["name"]: rec for rec in g._nodes}

    def deps(name):
        return {e[0] for p in by[name]["inputs"] if p["label"] == combined.DEP_PIN for e in p["edges"]}

    gets, writes = g.terrain["get"], g.terrain["write"]
    assert writes.keys() == {1, 7, 16}
    for n, nodes in gets.items():
        for node in nodes:
            assert deps(node) == {w for m in writes if m < n for w in writes[m]}
    for n, nodes in writes.items():
        for node in nodes:
            assert deps(node) == {q for m in gets if m < n for q in gets[m]}


def test_graph_is_acyclic(g):
    by = {rec["name"]: rec for rec in g._nodes}
    state = {}

    def visit(name):
        if state.get(name) == 1:
            raise AssertionError("cycle through %s" % name)
        if state.get(name) == 2:
            return
        state[name] = 1
        for p in by[name]["inputs"]:
            for e in p["edges"]:
                visit(e[0])
        state[name] = 2

    for name in by:
        visit(name)


def test_layout_bands_do_not_overlap(g):
    ir = g.to_ir(official)
    pos, boxes = combined.positions(ir)
    assert set(pos) == {n["name"] for n in ir["nodes"]}
    ordered = [boxes[k] for k in sorted(boxes)]
    assert len(ordered) == 18
    assert all(a[3] < b[1] for a, b in zip(ordered, ordered[1:]))


def test_component_overrides_are_renamed():
    out = combined.component_overrides({"PCG_3_1_1_Districts": {"SmallMediumThreshold": 1.0}})
    assert out == {"S06_SmallMediumThreshold": 1.0}


def test_unprefixed_reads_own_stage_only():
    assert stage_api.unprefixed({"S09_Seed": 7, "S09_debug": False}, 9) == {"Seed": 7, "debug": False}
    assert stage_api.unprefixed({"Seed": 3}, 9) == {"Seed": 3}
    with pytest.raises(stage_api.StageError):
        stage_api.unprefixed({"S10_Seed": 7}, 9)


def test_short_names():
    assert combined.short(7) == "Roads"
    assert combined.short(15) == "MainTower_Visuals"
    assert [combined.category(s[0]) for s in stages.STAGES][:2] == ["01 Terrain", "02 BG_Buildings"]
