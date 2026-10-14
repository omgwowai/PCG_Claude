import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_library.py -- write Content/Python/pypcg/library.json: the real input/output pins and
# parameters of every subgraph the 18 stage graphs use, the pins of every native node class,
# and the seed a freshly created node of each class gets (UPCGSettings seeds new nodes from a
# type-name hash; the comparator drops a seed equal to it).
# Reads the official IR snapshots written by pypcg_extract.py. Uses one transient graph.

EXTRA_CLASSES = ("PCGRerouteSettings", "PCGNamedRerouteDeclarationSettings", "PCGNamedRerouteUsageSettings",
                 "PCGUserParameterGetSettings", "PCGGenericUserParameterGetSettings",
                 "PCGSubgraphSettings", "PCGLoopSettings")


def _labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


def run():
    from pypcg import extract, ir as pir, stages
    snaps = [pir.load(os.path.join(_REPO, "Tools/pypcg/official_ir", n + ".json")) for n in stages.names()]
    seen_sub, seen_cls = {}, {}
    for g in snaps:
        for n in g["nodes"]:
            if n["name"] in pir.IO_NODES:
                continue
            ins = [p["label"] for p in n["inputs"]]
            outs = list(n.get("outputs", []))
            if n.get("subgraph"):
                e = seen_sub.setdefault(pir.alias_of(n["subgraph"]), {"path": n["subgraph"], "inputs": set(), "outputs": set()})
            else:
                e = seen_cls.setdefault(n["class"], {"inputs": set(), "outputs": set()})
            e["inputs"].update(ins)
            e["outputs"].update(outs)
    tmp = unreal.new_object(unreal.PCGGraph, unreal.find_package("/Engine/Transient"), "PYPCG_LIBRARY_PROBE")
    lib = {"subgraphs": {}, "classes": {}, "io": {}, "fresh_seeds": {}}
    sub_cls = unreal.load_class(None, "/Script/PCG.PCGSubgraphSettings")
    for alias, e in sorted(seen_sub.items()):
        sg = unreal.EditorAssetLibrary.load_asset(e["path"].split(".")[0])
        if sg is None:
            raise RuntimeError("cannot load subgraph " + e["path"])
        node, st = tmp.add_node_of_type(sub_cls)
        st.set_subgraph(sg)
        params = {p["name"]: p["type"] for p in extract.export(sg)["params"]}
        lib["subgraphs"][alias] = {"path": e["path"],
                                   "inputs": sorted(set(_labels(node, "input_pins")) | e["inputs"]),
                                   "outputs": sorted(set(_labels(node, "output_pins")) | e["outputs"]),
                                   "params": params}
    for cls_name in sorted(set(seen_cls) | set(EXTRA_CLASSES)):
        cls = unreal.load_class(None, "/Script/PCG." + cls_name)
        if cls is None:
            raise RuntimeError("no class " + cls_name)
        node, st = tmp.add_node_of_type(cls)
        e = seen_cls.get(cls_name, {"inputs": set(), "outputs": set()})
        lib["classes"][cls_name] = {"inputs": sorted(set(_labels(node, "input_pins")) | e["inputs"]),
                                    "outputs": sorted(set(_labels(node, "output_pins")) | e["outputs"])}
        lib["fresh_seeds"][cls_name] = int(st.get_editor_property("seed"))
    inp, outp = tmp.get_input_node(), tmp.get_output_node()
    lib["io"] = {"input_node_inputs": _labels(inp, "input_pins"), "input_node_outputs": _labels(inp, "output_pins"),
                 "output_node_inputs": _labels(outp, "input_pins"), "output_node_outputs": _labels(outp, "output_pins")}
    lib["fresh_seeds"]["PCGGraphInputOutputSettings"] = int(inp.get_settings().get_editor_property("seed"))
    path = os.path.join(_PY, "pypcg", "library.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lib, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return {"subgraphs": len(lib["subgraphs"]), "classes": len(lib["classes"]), "io": lib["io"], "path": path}


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
