# tl_spike_graph_api.py -- THROWAWAY SPIKE. Can a PCG graph with attribute
# maths be authored entirely from Python? Builds /Game/PCG/TL/_Spike_GraphApi
# (deleted again with {"clear": true}) and reports, per question:
#   Q1 attribute selectors: set input_source1 / output_target on a MetadataMaths
#      node (struct import_text vs set_editor_property of a new selector)
#   Q2 constants: CreateAttributeSet with a Double value via attribute_types
#   Q3 inline pin defaults on a metadata op (DefaultValues is a private UPROPERTY)
#   Q4 edge creation to a metadata op's InB pin, verified by edge count
#   Q5 string constants (for grammar rewriting) and MetadataStringOp Replace
import json

args = mcp_args or {}
PATH = "/Game/PCG/TL/_Spike_GraphApi"


def cls(name):
    return unreal.load_class(None, "/Script/PCG." + name)


def labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


def main():
    EAL = unreal.EditorAssetLibrary
    if args.get("clear"):
        return {"deleted": EAL.delete_asset(PATH) if EAL.does_asset_exist(PATH) else "absent"}
    R = {}
    if EAL.does_asset_exist(PATH):
        EAL.delete_asset(PATH)
    at = unreal.AssetToolsHelpers.get_asset_tools()
    g = at.create_asset("_Spike_GraphApi", "/Game/PCG/TL", unreal.PCGGraph, unreal.PCGGraphFactory())
    if g is None:
        return {"error": "create_asset returned None"}

    # Q1 selectors
    mnode, ms = g.add_node_of_type(cls("PCGMetadataMathsSettings"))
    R["maths_props"] = [p for p in dir(ms) if not p.startswith("_") and ("source" in p or "target" in p or "operation" in p or "default" in p)]
    sel = ms.get_editor_property("input_source1")
    R["selector_type"] = type(sel).__name__
    R["selector_methods"] = [m for m in dir(sel) if not m.startswith("_")][:40]
    try:
        ok = sel.import_text("PCGBegin(NextAngle)PCGEnd") if hasattr(sel, "import_text") else None
        ms.set_editor_property("input_source1", sel)
        R["q1_import_text"] = str(ms.get_editor_property("input_source1").export_text()) if hasattr(sel, "export_text") else str(ok)
    except Exception as e:
        R["q1_import_text"] = "ERR %s: %s" % (type(e).__name__, e)
    try:
        s2 = unreal.PCGAttributePropertyInputSelector()
        if hasattr(s2, "set_attribute_name"):
            s2.set_attribute_name("Foo")
        ms.set_editor_property("input_source2", s2)
        R["q1_new_selector"] = ms.get_editor_property("input_source2").export_text()
    except Exception as e:
        R["q1_new_selector"] = "ERR %s: %s" % (type(e).__name__, e)
    try:
        o = ms.get_editor_property("output_target")
        o.import_text("PCGBegin(HalfAngle)PCGEnd")
        ms.set_editor_property("output_target", o)
        R["q1_output"] = ms.get_editor_property("output_target").export_text()
    except Exception as e:
        R["q1_output"] = "ERR %s: %s" % (type(e).__name__, e)
    try:
        ms.set_editor_property("operation", unreal.PCGMetadataMathsOperation.DIVIDE)
        R["q1_operation"] = str(ms.get_editor_property("operation"))
    except Exception as e:
        R["q1_operation"] = "ERR %s" % e
    R["maths_inputs"] = labels(mnode, "input_pins")

    # Q2 constants
    cnode, cs = g.add_node_of_type(cls("PCGCreateAttributeSetSettings"))
    try:
        t = cs.get_editor_property("attribute_types")
        R["const_types_fields"] = [p for p in dir(t) if not p.startswith("_")][:30]
        t.import_text("(Type=Double,DoubleValue=2.000000)")
        cs.set_editor_property("attribute_types", t)
        o = cs.get_editor_property("output_target"); o.import_text("PCGBegin(Two)PCGEnd")
        cs.set_editor_property("output_target", o)
        R["q2_const"] = cs.get_editor_property("attribute_types").export_text()[:160]
    except Exception as e:
        R["q2_const"] = "ERR %s: %s" % (type(e).__name__, e)
    R["const_outputs"] = labels(cnode, "output_pins")

    # Q3 inline defaults
    R["q3_has_default_values_prop"] = False
    for name in ("default_values", "DefaultValues"):
        try:
            ms.get_editor_property(name)
            R["q3_has_default_values_prop"] = name
        except Exception as e:
            R["q3_err_" + name] = str(e)[:120]
    R["q3_setter_methods"] = [m for m in dir(ms) if "default" in m.lower()]

    # Q4 edges
    before = len(g.get_all_edges()) if hasattr(g, "get_all_edges") else None
    g.add_edge(cnode, "Out", mnode, "InB")
    after = len(g.get_all_edges()) if hasattr(g, "get_all_edges") else None
    R["q4_edges"] = [before, after]

    # Q5 string op
    snode, ss = g.add_node_of_type(cls("PCGMetadataStringOpSettings"))
    try:
        ss.set_editor_property("operation", unreal.PCGMetadataStringOperation.REPLACE)
        R["q5_string_op"] = str(ss.get_editor_property("operation"))
        R["q5_inputs"] = labels(snode, "input_pins")
    except Exception as e:
        R["q5_string_op"] = "ERR %s: %s" % (type(e).__name__, e)
    c2, cs2 = g.add_node_of_type(cls("PCGCreateAttributeSetSettings"))
    try:
        t = cs2.get_editor_property("attribute_types")
        t.import_text('(Type=String,StringValue="[FC")')
        cs2.set_editor_property("attribute_types", t)
        R["q5_string_const"] = cs2.get_editor_property("attribute_types").export_text()[:200]
    except Exception as e:
        R["q5_string_const"] = "ERR %s: %s" % (type(e).__name__, e)

    R["saved"] = EAL.save_asset(PATH, only_if_is_dirty=False)
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
