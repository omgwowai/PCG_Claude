import copy

import pytest

from pypcg import compare

FRESH = {"PCGRerouteSettings": 111, "PCGSubgraphSettings": 222, "PCGGraphInputOutputSettings": 333}


def node(name, cls="PCGRerouteSettings", title="", inputs=(), **extra):
    rec = {"name": name, "class": cls, "title": title, "settings": {},
           "inputs": [{"label": label, "edges": [list(e) for e in edges]} for label, edges in inputs]}
    rec.update(extra)
    return rec


def graph(*nodes, out=(), params=(), path="/Game/T.T"):
    return {"schema": 1, "graph": path, "graph_props": {}, "params": list(params), "comment_boxes": [],
            "nodes": [node("DefaultInputNode", "PCGGraphInputOutputSettings"),
                      node("DefaultOutputNode", "PCGGraphInputOutputSettings", inputs=[("Out", out)] if out else ())]
                     + list(nodes)}


def sub(name, alias, overrides=None, **kw):
    return node(name, "PCGSubgraphSettings", subgraph="/P/%s.%s" % (alias, alias),
                overrides=overrides or {}, **kw)


def chain(names):
    """a -> b: a Filter_Tags subgraph feeding a reroute that feeds the output."""
    a, b = names
    return graph(sub(a, "Filter_Tags", {"FilteredInputTags": "Lots"}, title="Filter"),
                 node(b, inputs=[("In", [(a, "Selected")])]),
                 out=[(b, "Out")])


def test_identical_graphs_with_different_names_have_no_diffs():
    assert compare.diff(chain(("n0", "n1")), chain(("Subgraph_7", "Reroute_2")), FRESH) == []


def test_changed_override_is_one_diff():
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    a["nodes"][2]["overrides"]["FilteredInputTags"] = "reservedLots"
    d = compare.diff(a, b, FRESH)
    assert [(x["kind"], x["field"], x["a"], x["b"]) for x in d] == [
        ("node", "overrides.FilteredInputTags", "reservedLots", "Lots")]


def test_edge_order_on_one_pin_matters():
    def g(order):
        return graph(node("s1", title="A"), node("s2", title="B"),
                     node("m", "PCGGatherSettings", inputs=[("In", [(s, "Out") for s in order])]),
                     out=[("m", "Out")])
    assert compare.diff(g(["s1", "s2"]), g(["s1", "s2"]), FRESH) == []
    d = compare.diff(g(["s1", "s2"]), g(["s2", "s1"]), FRESH)
    assert any(x["kind"] == "edge" and x["field"] == "inputs.In" for x in d)


def test_pin_order_inside_a_node_does_not_matter():
    a = graph(node("s1", title="A"), node("s2", title="B"),
              node("m", "PCGMetadataMathsSettings", inputs=[("InA", [("s1", "Out")]), ("InB", [("s2", "Out")])]),
              out=[("m", "Out")])
    b = copy.deepcopy(a)
    b["nodes"][4]["inputs"].reverse()
    assert compare.diff(a, b, FRESH) == []


def test_symmetric_reroutes_pair():
    # Review Focus 3: two untitled reroutes from one source into one Gather.
    def g(r1, r2):
        return graph(node("src", title="Src"), node(r1, inputs=[("In", [("src", "Out")])]),
                     node(r2, inputs=[("In", [("src", "Out")])]),
                     node("gather", "PCGGatherSettings", inputs=[("In", [(r1, "Out"), (r2, "Out")])]),
                     out=[("gather", "Out")])
    assert compare.diff(g("ra", "rb"), g("Reroute_9", "Reroute_3"), FRESH) == []


def test_bool_and_int_differ():
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    a["nodes"][3]["settings"]["bEnabled"] = False
    b["nodes"][3]["settings"]["bEnabled"] = 0
    assert compare.diff(a, b, FRESH)


def test_int_and_float_compare_by_value():
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    a["nodes"][2]["overrides"]["Size"] = 100000
    b["nodes"][2]["overrides"]["Size"] = 100000.0
    assert compare.diff(a, b, FRESH) == []
    b["nodes"][2]["overrides"]["Size"] = -1820.4246063232422
    a["nodes"][2]["overrides"]["Size"] = -1820.424606
    assert compare.diff(a, b, FRESH)


def test_fresh_seed_is_dropped_other_seeds_count():
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    b["nodes"][3]["settings"]["Seed"] = 111
    assert compare.diff(a, b, FRESH) == []
    b["nodes"][3]["settings"]["Seed"] = 5
    assert compare.diff(a, b, FRESH)


def test_node_ref_paths_normalise_to_names():
    a = graph(node("d", "PCGNamedRerouteDeclarationSettings", title="Lots"),
              node("u", "PCGNamedRerouteUsageSettings", title="Lots", settings={"Declaration": {"node_ref": "d"}},
                   inputs=[("In", [("d", "InvisiblePin")])]),
              out=[("u", "Out")], path="py")
    b = graph(node("Decl_1", "PCGNamedRerouteDeclarationSettings", title="Lots"),
              node("Use_4", "PCGNamedRerouteUsageSettings", title="Lots",
                   settings={"Declaration": "/Script/PCG.PCGNamedRerouteDeclarationSettings'/Game/T.T:Decl_1.PCGNamedRerouteDeclarationSettings_3'"},
                   inputs=[("In", [("Decl_1", "InvisiblePin")])]),
              out=[("Use_4", "Out")])
    assert compare.diff(a, b, FRESH) == []


def test_missing_node_is_reported():
    a = chain(("n0", "n1"))
    b = chain(("x", "y"))
    b["nodes"].append(node("extra", title="Debug"))
    kinds = [x["kind"] for x in compare.diff(a, b, FRESH)]
    assert kinds == ["missing_node"]


def test_params_tooltip_and_ignored_meta():
    p_py = {"name": "R", "type": "Double", "container": "None", "type_object": "", "value": 0.9,
            "category": "Road", "tooltip": "tip", "meta": {}}
    p_ue = {"name": "R", "type": "Double", "container": "None", "type_object": "", "value": 0.9,
            "category": "Road", "meta": {"Category": "Road"},
            "hier_meta": {"Values": [{"_structType": "/Script/StructUtilsEditor.PropertyBagPropertyMetadata_Common",
                                      "Tooltip": "tip", "bAdvanced": False}]}}
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    a["params"], b["params"] = [p_py], [p_ue]
    assert compare.diff(a, b, FRESH) == []
    p_py["value"] = 0.5
    assert [x["field"] for x in compare.diff(a, b, FRESH)] == ["params.R.value"]


def test_undeclared_changes_respects_sites():
    a, b = chain(("n0", "n1")), chain(("n0", "n1"))
    a["nodes"][2]["overrides"]["FilteredInputTags"] = "Other"
    a["sites"] = [{"where": "n0.overrides.FilteredInputTags", "kind": "knob", "knob": "K"}]
    assert compare.undeclared_changes(a, b) == []
    a["sites"] = []
    assert compare.undeclared_changes(a, b) == ["n0.overrides.FilteredInputTags"]


def test_layout_membership_mismatch_is_reported():
    a, b = chain(("n0", "n1")), chain(("x", "y"))
    for g in (a, b):
        g["nodes"][2]["pos"], g["nodes"][3]["pos"] = [0, 0], [400, 0]
        g["nodes"][0]["pos"], g["nodes"][1]["pos"] = [-600, 0], [800, 0]
        g["comment_boxes"] = [{"NodePosX": -50, "NodePosY": -50, "NodeWidth": 200, "NodeHeight": 200,
                               "NodeComment": "Box"}]
    assert compare.diff(a, b, FRESH, check_layout=True) == []
    a["nodes"][3]["pos"] = [100, 0]          # moves the reroute into the box
    fields = [x["field"] for x in compare.diff(a, b, FRESH, check_layout=True)]
    assert "comment_boxes[0].members" in fields


def test_individualisation_pairs_automorphic_branches():
    # One source feeds two identical untitled dead-end reroutes plus the output: colour
    # refinement alone can't tell the two reroutes apart (they're automorphic), so match()
    # must fall into its individualisation loop to pair them at all.
    def g(r1, r2):
        return graph(node("src", title="Src"), node(r1, inputs=[("In", [("src", "Out")])]),
                     node(r2, inputs=[("In", [("src", "Out")])]),
                     out=[("src", "Out")])
    compare._INDIVIDUALISED[0] = 0
    assert compare.diff(g("ra", "rb"), g("Reroute_9", "Reroute_3"), FRESH) == []
    assert compare._INDIVIDUALISED[0] >= 1


def test_colours_do_not_collide_on_hash_negative_one_and_two():
    # hash(-1) == hash(-2) in CPython; a colour scheme built from raw hash() would merge two
    # siblings whose only difference is an X=-1 vs X=-2 setting into the same equivalence class.
    def g(x1, x2):
        return graph(node("s1", title="A", settings={"X": x1}), node("s2", title="A", settings={"X": x2}),
                     node("m", "PCGGatherSettings", inputs=[("In", [("s1", "Out"), ("s2", "Out")])]),
                     out=[("m", "Out")])
    assert compare.diff(g(-1, -2), g(-1, -2), FRESH) == []


def test_view_rejects_duplicate_node_names():
    a = chain(("n0", "n1"))
    a["nodes"].append(node("n0", title="Dupe"))
    with pytest.raises(ValueError, match="duplicate node name"):
        compare.view(a, FRESH)


def test_missing_key_differs_from_explicit_null():
    a, b = chain(("n0", "n1")), chain(("n0", "n1"))
    b["nodes"][2]["overrides"]["Extra"] = None
    d = compare.diff(a, b, FRESH)
    assert [(x["field"], x["a"], x["b"]) for x in d] == [("overrides.Extra", "<missing>", None)]
