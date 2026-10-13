# pyg_probe_export_t3d_all.py -- READ-ONLY. Export each of the 18 City Sample
# stage graphs to T3D text under Saved/graph_dumps/<name>.t3d (UTF-16), the only
# serialization that carries private UPROPERTYs Python cannot read (inline pin
# defaults, subgraph parameter overrides, actor references). Returns sizes only.
# Args: {"graphs": ["<asset path>", ...]} (default: the 18 stage graphs)
import json
import os

STAGES = [
    "PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
    "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
    "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
    "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
    "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
    "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
    "PCG_5_1_CityEdge", "PCG_5_2_OuterForest",
]


def export(path):
    obj = unreal.EditorAssetLibrary.load_asset(path)
    if obj is None:
        return {"asset": path, "fatal": "not loadable"}
    out = os.path.join(unreal.Paths.project_saved_dir(), "graph_dumps", path.rsplit("/", 1)[-1] + ".t3d")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    task = unreal.AssetExportTask()
    task.set_editor_property("object", obj)
    task.set_editor_property("filename", out)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    task.set_editor_property("exporter", None)
    ok = unreal.Exporter.run_asset_export_task(task)
    return {"asset": path, "ok": ok, "size": os.path.getsize(out) if os.path.exists(out) else 0}


def main():
    args = mcp_args or {}
    paths = args.get("graphs") or ["/CitySamplePCG/Levels/PCG/" + n for n in STAGES]
    return [export(p) for p in paths]


mcp_result = json.loads(json.dumps(main(), default=str))
