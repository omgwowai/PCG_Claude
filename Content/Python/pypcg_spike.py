# pypcg_spike.py -- Task 2 spike. Writes ONLY /Game/PyPCG/_Spike/PyPCG_SpikeGraph.
# Args: {"phase": "build" | "reload" | "clear"}
#   build  : make the graph (params, getter, pin default, comment box, named reroute, enum override), save it
#   reload : reload the package from disk and export it again; compare with the export taken at build
#   clear  : delete the spike asset
import gc
import json
import os

import unreal

PATH = "/Game/PyPCG/_Spike/PyPCG_SpikeGraph"
SNAP = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pypcg_spike_build.json")
L = unreal.PyPCGToolsLibrary


def _pin_labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


def _edges_on(node, label):
    for p in node.get_editor_property("input_pins"):
        if str(p.get_editor_property("properties").get_editor_property("label")) == label:
            return len(p.get_editor_property("edges"))
    return -1


def build():
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(PATH):
        return {"abort": "spike asset exists; run phase clear first"}
    pkg, name = PATH.rsplit("/", 1)
    g = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, pkg, unreal.PCGGraph, unreal.PCGGraphFactory())
    if g is None:
        return {"abort": "create_asset returned None"}
    R = {}
    R["params"] = L.set_graph_user_parameters(g, json.dumps({"params": [
        {"name": "Ratio", "type": "Double", "container": "None", "type_object": "", "meta": {},
         "value": 0.9, "category": "Road Parameters", "tooltip": "spike tip"}]}))
    getter, gs = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGUserParameterGetSettings"))
    R["bind"] = L.bind_user_parameter_getter(gs, "Ratio")
    maths, ms = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGMetadataMathsSettings"))
    R["pin_default"] = L.set_pin_default_value(ms, 1, "Double", json.dumps({"v": 2.0}), True, True)
    R["comment"] = L.set_node_comment(maths, "spike comment", True, False)
    maths.set_node_position(0, 0)
    getter.set_node_position(-300, 0)
    R["boxes"] = L.set_graph_comment_boxes(g, json.dumps({"boxes": [
        {"NodePosX": -400, "NodePosY": -100, "NodeWidth": 600, "NodeHeight": 300,
         "NodeComment": "SPIKE BOX", "FontSize": 18}]}))
    # Q3: named reroute declaration -> usage
    decl, ds = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGNamedRerouteDeclarationSettings"))
    use, us = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGNamedRerouteUsageSettings"))
    R["decl_out_pins"] = _pin_labels(decl, "output_pins")
    R["use_in_pins"] = _pin_labels(use, "input_pins")
    R["set_declaration"] = L.set_properties_json(us, json.dumps({"Declaration": ds.get_path_name()}))
    before = _edges_on(use, "In")
    g.add_edge(decl, "InvisiblePin", use, "In")
    R["invisible_edge_created"] = _edges_on(use, "In") == before + 1
    # Q4: user-defined enum override
    trace, ts = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGSubgraphSettings"))
    ts.set_subgraph(unreal.load_asset("/PCGPrimitives/Primitives/Trace/Trace_Bound_Footprint"))
    inst = ts.get_editor_property("subgraph_instance")
    R["enum_set"] = L.set_instance_parameter(inst, "PlanarSurface", json.dumps({"v": "NewEnumerator4"}))
    R["enum_read"] = json.loads(L.export_instance_overrides(inst)).get("PlanarSurface")
    ir = json.loads(L.export_graph_ir(g))
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    with open(SNAP, "w", encoding="utf-8") as fh:
        json.dump(ir, fh, indent=1, sort_keys=True)
    R["saved"] = bool(EAL.save_asset(PATH, only_if_is_dirty=False))
    return R


def reload():
    pkg = unreal.find_package(PATH)
    R = {}
    try:
        unreal.EditorLoadingAndSavingUtils.reload_packages([pkg], unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
        R["reloaded"] = True
    except Exception as ex:
        R["reload_error"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])
    g = unreal.EditorAssetLibrary.load_asset(PATH)
    after = json.loads(L.export_graph_ir(g))
    with open(SNAP, encoding="utf-8") as fh:
        before = json.load(fh)
    keys = ("params", "comment_boxes", "nodes", "graph_props")
    R["equal"] = {k: json.dumps(before.get(k), sort_keys=True) == json.dumps(after.get(k), sort_keys=True) for k in keys}
    if not all(R["equal"].values()):
        diff_path = SNAP.replace(".json", "_after.json")
        with open(diff_path, "w", encoding="utf-8") as fh:
            json.dump(after, fh, indent=1, sort_keys=True)
        R["after_written"] = diff_path
    # Q4 follow-up: confirm the override we set is not just the PlanarSurface *default*
    # (which would make "enum_read" == "Top" a silent no-op rather than a real override).
    parent = unreal.load_asset("/PCGPrimitives/Primitives/Trace/Trace_Bound_Footprint")
    parent_ir = json.loads(L.export_graph_ir(parent))
    parent_default = None
    for p in parent_ir.get("params", []):
        if p.get("name") == "PlanarSurface":
            parent_default = p.get("value")
            break
    R["parent_default_planar_surface"] = parent_default
    R["enum_override_confirmed"] = (parent_default is not None) and (parent_default != "Top")
    return R


def clear():
    ok = unreal.EditorAssetLibrary.delete_asset(PATH)
    return {"deleted": bool(ok), "exists": unreal.EditorAssetLibrary.does_asset_exist(PATH)}


def main():
    phase = (mcp_args or {}).get("phase", "build")
    return {"build": build, "reload": reload, "clear": clear}[phase]()


mcp_result = json.loads(json.dumps(main(), default=str))
gc.collect()
