import gc
import json

import unreal

# pyworld_probe_examples.py -- READ ONLY. How the engine's example graphs wire the building grammar
# (Assign_ShapeGrammarDefinition on a footprint) and a mesh spawner fed by a per-point mesh attribute.

WANT = ("Assign_ShapeGrammarDefinition", "Spawn_Assets", "Create_Spline_Shape", "Transform_Areas_Contract",
        "Transform_Offset", "Create_Mesh_Planar", "Fill_Areas_Uniformly", "Assign_Assets")


def run():
    from pypcg import extract
    out = {}
    for path in ["/PCGPrimitives/Examples/Buildings/BuildingBlock_StaggeredSquare",
                 "/PCGPrimitives/Examples/City/City_Generator_Steps_5_Buildings"]:
        ir = extract.export_path(path)
        rows = []
        for n in ir["nodes"]:
            sg = (n.get("subgraph") or "").split("/")[-1].split(".")[0]
            if sg in WANT or n["class"] in ("PCGStaticMeshSpawnerSettings",):
                rows.append({"name": n["name"], "title": n.get("title"), "sub": sg or n["class"],
                             "overrides": n.get("overrides"),
                             "inputs": [[p["label"], p["edges"]] for p in n.get("inputs", []) if p["edges"]]})
        out[path] = {"params": [[p["name"], p["type"], p["value"]] for p in ir["params"]], "nodes": rows}
    sgd = unreal.EditorAssetLibrary.load_asset("/PCGPrimitives/Grammar/DataAsset/Bldg_Demo/SGD_Bldg_Demo")
    out["sgd_class"] = sgd.get_class().get_name() if sgd else None
    if sgd:
        props = {}
        for name in dir(sgd):
            if name.startswith("_"):
                continue
            try:
                v = sgd.get_editor_property(name)
            except Exception:
                continue
            props[name] = str(v)[:400]
        out["sgd_props"] = props
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
